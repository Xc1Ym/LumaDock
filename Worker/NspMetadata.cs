// LumaDock's metadata protocol extension. Compiled only in a private snapshot
// of the selected nxnative reader; the engine itself is never distributed here.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using LibHac.Common;
using LibHac.Common.Keys;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Spl;
using LibHac.Tools.Fs;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;

static partial class P {
    static byte[] LumaDockRead(IFileSystem fs, string path) {
        using var file = new UniqueRef<IFile>();
        fs.OpenFile(ref file.Ref, path.ToU8Span(), OpenMode.Read).ThrowIfFailure();
        file.Get.GetSize(out long size).ThrowIfFailure();
        if (size < 0 || size > 16 * 1024 * 1024) throw new IOException("Invalid metadata length");
        byte[] result = new byte[size];
        file.Get.Read(out long read, 0, result, ReadOption.None).ThrowIfFailure();
        if (read != size) throw new IOException("Incomplete metadata");
        return result;
    }
    // Keep content IDs: selecting by NCA type alone loses updates in merged containers.
    static Dictionary<string,Nca> LumaDockContainer(KeySet keys, string path) {
        IFileSystem fs;
        var storage = new LocalStorage(path, FileAccess.Read);
        byte[] magic = new byte[4]; storage.Read(0x100, magic).ThrowIfFailure();
        if (System.Text.Encoding.ASCII.GetString(magic) == "HEAD") {
            var xci = new Xci(keys, storage);
            if (!xci.HasPartition(XciPartitionType.Secure)) throw new IOException("No secure partition");
            fs = xci.OpenPartition(XciPartitionType.Secure);
        } else {
            var pfs = new PartitionFileSystem(); pfs.Initialize(storage).ThrowIfFailure(); fs = pfs;
        }
        var contents = new Dictionary<string,IStorage>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in fs.EnumerateEntries("*", SearchOptions.Default)) {
            if (entry.Type != DirectoryEntryType.File) continue;
            using var file = new UniqueRef<IFile>();
            fs.OpenFile(ref file.Ref, entry.FullPath.ToU8Span(), OpenMode.Read).ThrowIfFailure();
            var item = file.Release().AsStorage();
            if (entry.Name.EndsWith(".tik", StringComparison.OrdinalIgnoreCase)) {
                byte[] ticket = new byte[0x2c0]; item.Read(0, ticket).ThrowIfFailure();
                if (ticket[0x281] != 0) throw new IOException("Personal ticket is unsupported");
                keys.ExternalKeySet.Add(new RightsId(ticket.AsSpan(0x2a0,16)), new AccessKey(ticket.AsSpan(0x180,16))).ThrowIfFailure();
            } else if (entry.Name.EndsWith(".nca", StringComparison.OrdinalIgnoreCase)) {
                string id = entry.Name.Split('.')[0];
                if (id.Length != 32 || !id.All(Uri.IsHexDigit)) throw new IOException("Invalid content ID");
                contents.Add(id, item);
            }
        }
        return contents.ToDictionary(x => x.Key, x => new Nca(keys,x.Value), StringComparer.OrdinalIgnoreCase);
    }
    sealed class LumaDockContent {
        public ulong Title, Base;
        public uint Version;
        public string Kind;
        public List<Nca> Ncas = new List<Nca>();
    }
    static List<LumaDockContent> LumaDockContents(Dictionary<string,Nca> container) {
        var result = new List<LumaDockContent>();
        foreach (var meta in container.Values.Where(x => x.Header.ContentType == NcaContentType.Meta)) {
            var fs = meta.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.ErrorOnInvalid);
            foreach (var entry in fs.EnumerateEntries("*", SearchOptions.RecurseSubdirectories)) {
                if (!entry.Name.EndsWith(".cnmt", StringComparison.OrdinalIgnoreCase)) continue;
                byte[] raw = LumaDockRead(fs,entry.FullPath);
                if (raw.Length < 0x20) throw new IOException("Invalid CNMT");
                string kind = raw[12] switch { 0x80 => "base", 0x81 => "update", 0x82 => "dlc", _ => null };
                if (kind == null) continue;
                int extended = BitConverter.ToUInt16(raw,14), count = BitConverter.ToUInt16(raw,16);
                int offset = 0x20 + extended;
                if (offset + count * 0x38 > raw.Length || (kind != "base" && extended < 8)) throw new IOException("Short CNMT");
                ulong title = BitConverter.ToUInt64(raw,0);
                var content = new LumaDockContent { Title=title, Base=kind == "base" ? title : BitConverter.ToUInt64(raw,0x20),
                    Version=BitConverter.ToUInt32(raw,8), Kind=kind };
                for (int i=0; i<count; i++) {
                    string id = Convert.ToHexString(raw,offset+i*0x38+0x20,16).ToLowerInvariant();
                    if (container.TryGetValue(id,out var nca)) content.Ncas.Add(nca);
                    else if (raw[offset+i*0x38+0x36] != 6) throw new IOException("Missing content NCA"); // optional delta fragment
                }
                result.Add(content);
            }
        }
        if (result.Count == 0) throw new IOException("No application metadata");
        return result;
    }
    static ulong? LumaDockTitle;
    static uint? LumaDockVersion;
    static string[] LumaDockArgs(string[] args) {
        var kept = new List<string>();
        foreach (string arg in args) {
            if (arg.StartsWith("--lumadock-title=")) LumaDockTitle = Convert.ToUInt64(arg.Substring("--lumadock-title=".Length),16);
            else if (arg.StartsWith("--lumadock-version=")) LumaDockVersion = uint.Parse(arg.Substring("--lumadock-version=".Length));
            else kept.Add(arg);
        }
        return kept.ToArray();
    }
    static List<Nca> LumaDockSelected(KeySet keys, string path, string kind) {
        if (!LumaDockTitle.HasValue || !LumaDockVersion.HasValue) throw new IOException("Missing content selection");
        var candidates = LumaDockContents(LumaDockContainer(keys,path));
        return candidates.Single(x => x.Kind == kind && (kind == "dlc" ? x.Title : x.Base) == LumaDockTitle.Value
            && x.Version == (kind == "base" ? 0 : LumaDockVersion.Value)).Ncas;
    }
    static int LumaDockInspect(string[] args) {
        try {
            var keys = ExternalKeyReader.ReadKeyFile(args[0]);
            var packages = new List<object>();
            foreach (var content in LumaDockContents(LumaDockContainer(keys,args[2]))) {
                string name = "", display = "";
                var control = Pick(content.Ncas, NcaContentType.Control);
                if (control != null) {
                    byte[] nacp = Nacp(control);
                    if (nacp.Length < 0x3070) throw new IOException("Short NACP");
                    name = TitleName(nacp);
                    display = System.Text.Encoding.UTF8.GetString(nacp,0x3060,16).TrimEnd('\0');
                    if (args.Length > 3) {
                        Directory.CreateDirectory(args[3]);
                        var (icon, _) = Icon(control);
                        if (icon != null) File.WriteAllBytes(System.IO.Path.Combine(args[3],content.Title.ToString("X16")+".jpg"),icon);
                    }
                }
                var builds = new Dictionary<string,string>();
                var program = Pick(content.Ncas, NcaContentType.Program);
                if (program != null) {
                    var code = program.OpenFileSystem(NcaSectionType.Code, IntegrityCheckLevel.ErrorOnInvalid);
                    foreach (var file in code.EnumerateEntries("*", SearchOptions.Default)) {
                        if (file.Type != DirectoryEntryType.File || file.Size < 0x60) continue;
                        using var handle = new UniqueRef<IFile>();
                        code.OpenFile(ref handle.Ref,file.FullPath.ToU8Span(),OpenMode.Read).ThrowIfFailure();
                        byte[] header = new byte[0x60];
                        handle.Get.Read(out long read,0,header,ReadOption.None).ThrowIfFailure();
                        if (read == header.Length && System.Text.Encoding.ASCII.GetString(header,0,4) == "NSO0")
                            builds[file.Name] = Convert.ToHexString(header,0x40,16).ToLowerInvariant();
                    }
                }
                packages.Add(new { titleId=content.Title.ToString("X16"), baseId=content.Base.ToString("X16"),
                    version=content.Version, type=content.Kind, name, display, builds });
            }
            Console.WriteLine(JsonSerializer.Serialize(new { schema=2, packages }));
            return 0;
        } catch (Exception) {
            Console.Error.WriteLine("Game metadata could not be decrypted or verified. Check keys, file integrity and engine format support.");
            return 3;
        }
    }
}
