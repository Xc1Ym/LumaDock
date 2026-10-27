// Export the unchanged original Assets/LumaNX.png artwork into app icon formats.
// AppKit / ImageIO only. All sizes preserve the artwork and its transparency.
import AppKit
import ImageIO
let root=URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
let assets=root.appendingPathComponent("Assets"),iconset=root.appendingPathComponent("work/LumaNX.iconset")
let source=assets.appendingPathComponent("LumaNX.png")
guard let input=CGImageSourceCreateWithURL(source as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(input,0,nil),image.width==image.height else {
    fatalError("Assets/LumaNX.png must contain the square canonical icon artwork")
}
try FileManager.default.createDirectory(at:iconset,withIntermediateDirectories:true)
func render(_ size:Int)->Data {
    let c=CGContext(data:nil,width:size,height:size,bitsPerComponent:8,bytesPerRow:size*4,
                    space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.interpolationQuality = .high
    c.draw(image,in:CGRect(x:0,y:0,width:size,height:size))
    return NSBitmapImageRep(cgImage:c.makeImage()!).representation(using:.png,properties:[:])!
}
let variants:[(String,Int)]=[("icon_16x16",16),("icon_16x16@2x",32),("icon_32x32",32),("icon_32x32@2x",64),
    ("icon_128x128",128),("icon_128x128@2x",256),("icon_256x256",256),("icon_256x256@2x",512),
    ("icon_512x512",512),("icon_512x512@2x",1024)]
for(name,size)in variants{try render(size).write(to:iconset.appendingPathComponent(name+".png"))}
// Modern ICNS stores PNG chunks; direct export also works in build sandboxes.
func u32be(_ x:UInt32)->Data{var n=x.bigEndian;return Data(bytes:&n,count:4)}
let iconTypes=["icp4","ic11","icp5","ic12","ic07","ic13","ic08","ic14","ic09","ic10"]
var chunks=Data()
for(type,variant)in zip(iconTypes,variants){
    let data=try Data(contentsOf:iconset.appendingPathComponent(variant.0+".png"))
    chunks.append(Data(type.utf8));chunks.append(u32be(UInt32(data.count+8)));chunks.append(data)
}
var icns=Data("icns".utf8);icns.append(u32be(UInt32(chunks.count+8)));icns.append(chunks)
try icns.write(to:assets.appendingPathComponent("LumaNX.icns"))
func u16(_ x:UInt16)->Data{var n=x.littleEndian;return Data(bytes:&n,count:2)}
func u32(_ x:UInt32)->Data{var n=x.littleEndian;return Data(bytes:&n,count:4)}
let sizes=[16,24,32,48,64,128,256],images=[16,24,32,48,64,128,256].map(render)
var ico=Data([0,0,1,0]);ico.append(u16(UInt16(sizes.count)));var offset=6+16*sizes.count
for(size,data)in zip(sizes,images){
    ico.append(Data([size==256 ? 0:UInt8(size),size==256 ? 0:UInt8(size),0,0]))
    ico.append(u16(1));ico.append(u16(32));ico.append(u32(UInt32(data.count)));ico.append(u32(UInt32(offset)));offset+=data.count
}
for data in images{ico.append(data)}
try ico.write(to:assets.appendingPathComponent("LumaNX.ico"))
print("Exported original artwork to 16–1024 px ICNS and 7-size ICO; source PNG preserved")
