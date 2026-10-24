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
    static int LumaDockInspect(string[] args) {
        try {
            var keys = ExternalKeyReader.ReadKeyFile(args[0]);
            var package = OpenNsp(keys, args[2]);
            var meta = Pick(package, NcaContentType.Meta) ?? throw new IOException("No content metadata");
            var filesystem = meta.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.ErrorOnInvalid);
            var entry = filesystem.EnumerateEntries("*", SearchOptions.RecurseSubdirectories).Single(e => e.Name.EndsWith(".cnmt", StringComparison.OrdinalIgnoreCase));
            byte[] cnmt = LumaDockRead(filesystem, entry.FullPath);
            if (cnmt.Length < 0x28) throw new IOException("Invalid CNMT");
            ulong title = BitConverter.ToUInt64(cnmt, 0);
            uint version = BitConverter.ToUInt32(cnmt, 8);
            string type = cnmt[12] switch { 0x80 => "base", 0x81 => "update", 0x82 => "dlc", _ => throw new IOException("Unsupported content type") };
            ulong baseTitle = type == "base" ? title : BitConverter.ToUInt64(cnmt, 0x20);
            string name = "", display = "";
            var control = Pick(package, NcaContentType.Control);
            if (control != null) {
                byte[] nacp = Nacp(control); name = TitleName(nacp);
                display = System.Text.Encoding.UTF8.GetString(nacp, 0x3060, 16).TrimEnd('\0');
                if (args.Length > 3) { var (icon, _) = Icon(control); if (icon != null) File.WriteAllBytes(args[3], icon); }
            }
            var builds = new Dictionary<string,string>();
            var program = Pick(package, NcaContentType.Program);
            if (program != null) {
                var code = program.OpenFileSystem(NcaSectionType.Code, IntegrityCheckLevel.ErrorOnInvalid);
                foreach (var file in code.EnumerateEntries("*", SearchOptions.Default)) {
                    using var handle = new UniqueRef<IFile>();
                    code.OpenFile(ref handle.Ref, file.FullPath.ToU8Span(), OpenMode.Read).ThrowIfFailure();
                    handle.Get.GetSize(out long size).ThrowIfFailure(); if (size < 0x60) continue;
                    byte[] header = new byte[0x60];
                    handle.Get.Read(out long read, 0, header, ReadOption.None).ThrowIfFailure();
                    if (read == header.Length && header[0]=='N' && header[1]=='S' && header[2]=='O' && header[3]=='0') builds[file.Name] = Convert.ToHexString(header,0x40,16).ToLowerInvariant();
                }
            }
            Console.WriteLine(JsonSerializer.Serialize(new { titleId=title.ToString("X16"), baseId=baseTitle.ToString("X16"), version, type, name, display, builds }));
            return 0;
        } catch (Exception) {
            Console.Error.WriteLine("Game metadata could not be decrypted or verified. Check keys, file integrity and engine format support.");
            return 3;
        }
    }
}
