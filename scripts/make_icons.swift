// Original LumaDock artwork. AppKit/CoreGraphics only; no third-party fonts or art.
import AppKit

let root = URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
let output = root.appendingPathComponent("Assets")
let iconset = root.appendingPathComponent("work/LumaDock.iconset")
try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
try FileManager.default.createDirectory(at:iconset,withIntermediateDirectories:true)
func rgb(_ r:CGFloat,_ g:CGFloat,_ b:CGFloat,_ a:CGFloat=1)->CGColor {CGColor(srgbRed:r,green:g,blue:b,alpha:a)}
func gradient(_ colors:[CGColor])->CGGradient {CGGradient(colorsSpace:CGColorSpace(name:CGColorSpace.sRGB)!,colors:colors as CFArray,locations:nil)!}
func render(_ size:Int)->Data {
    let c=CGContext(data:nil,width:size,height:size,bitsPerComponent:8,bytesPerRow:size*4,space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.scaleBy(x:CGFloat(size)/1024,y:CGFloat(size)/1024)
    c.setAllowsAntialiasing(true)
    let tile=CGPath(roundedRect:CGRect(x:80,y:80,width:864,height:864),cornerWidth:190,cornerHeight:190,transform:nil)
    c.saveGState()
    c.setShadow(offset:CGSize(width:0,height:-12),blur:24,color:rgb(0.02,0.16,0.22,0.22))
    c.addPath(tile);c.setFillColor(rgb(0.1,0.5,0.6));c.fillPath();c.restoreGState()
    c.saveGState();c.addPath(tile);c.clip()
    c.drawLinearGradient(gradient([rgb(0.11,0.29,0.53),rgb(0.02,0.62,0.65),rgb(0.44,0.89,0.85)]),start:CGPoint(x:800,y:100),end:CGPoint(x:210,y:950),options:[])
    c.drawRadialGradient(gradient([rgb(0.84,1,0.98,0.65),rgb(0.8,1,1,0)]),startCenter:CGPoint(x:230,y:900),startRadius:0,endCenter:CGPoint(x:230,y:900),endRadius:620,options:[])
    c.drawRadialGradient(gradient([rgb(0.25,0.42,0.98,0.4),rgb(0.25,0.42,0.98,0)]),startCenter:CGPoint(x:900,y:250),startRadius:0,endCenter:CGPoint(x:900,y:250),endRadius:540,options:[])
    c.restoreGState()
    let ribbon=CGMutablePath()
    ribbon.move(to:CGPoint(x:302,y:730));ribbon.addLine(to:CGPoint(x:414,y:784));ribbon.addLine(to:CGPoint(x:414,y:414));ribbon.addLine(to:CGPoint(x:726,y:414));ribbon.addLine(to:CGPoint(x:672,y:302));ribbon.addLine(to:CGPoint(x:302,y:302));ribbon.closeSubpath()
    c.saveGState();c.setShadow(offset:CGSize(width:10,height:-18),blur:28,color:rgb(0,0.13,0.28,0.3));c.addPath(ribbon);c.setFillColor(rgb(0.8,1,1,0.65));c.fillPath();c.restoreGState()
    c.saveGState();c.addPath(ribbon);c.clip();c.drawLinearGradient(gradient([rgb(0.63,0.95,1,0.72),rgb(1,1,1,0.98)]),start:CGPoint(x:700,y:300),end:CGPoint(x:310,y:800),options:[]);c.restoreGState()
    c.addPath(ribbon);c.setStrokeColor(rgb(1,1,1,0.75));c.setLineWidth(4);c.setLineJoin(.round);c.strokePath()
    // A translucent play facet floats above the dock-shaped ribbon.
    let play=CGMutablePath();play.move(to:CGPoint(x:507,y:504));play.addLine(to:CGPoint(x:507,y:713));play.addQuadCurve(to:CGPoint(x:530,y:725),control:CGPoint(x:507,y:739));play.addLine(to:CGPoint(x:706,y:623));play.addQuadCurve(to:CGPoint(x:706,y:596),control:CGPoint(x:732,y:610));play.addLine(to:CGPoint(x:530,y:494));play.addQuadCurve(to:CGPoint(x:507,y:504),control:CGPoint(x:507,y:480));play.closeSubpath()
    c.saveGState();c.setShadow(offset:CGSize(width:4,height:-12),blur:24,color:rgb(0,0.2,0.36,0.22));c.addPath(play);c.setFillColor(rgb(0.88,1,1,0.65));c.fillPath();c.restoreGState()
    c.saveGState();c.addPath(play);c.clip();c.drawLinearGradient(gradient([rgb(0.62,0.88,1,0.4),rgb(1,1,1,0.9)]),start:CGPoint(x:720,y:510),end:CGPoint(x:495,y:730),options:[]);c.restoreGState()
    c.addPath(play);c.setStrokeColor(rgb(1,1,1,0.85));c.setLineWidth(4);c.strokePath()
    c.addPath(CGPath(roundedRect:CGRect(x:83,y:83,width:858,height:858),cornerWidth:187,cornerHeight:187,transform:nil));c.setStrokeColor(rgb(1,1,1,0.32));c.setLineWidth(3);c.strokePath()
    let rep=NSBitmapImageRep(cgImage:c.makeImage()!)
    return rep.representation(using:.png,properties:[:])!
}
let variants:[(String,Int)]=[("icon_16x16",16),("icon_16x16@2x",32),("icon_32x32",32),("icon_32x32@2x",64),("icon_128x128",128),("icon_128x128@2x",256),("icon_256x256",256),("icon_256x256@2x",512),("icon_512x512",512),("icon_512x512@2x",1024)]
for (name,size) in variants {try render(size).write(to:iconset.appendingPathComponent(name+".png"))}
try render(1024).write(to:output.appendingPathComponent("LumaDock.png"))
let iconutil=Process();iconutil.executableURL=URL(fileURLWithPath:"/usr/bin/iconutil");iconutil.arguments=["-c","icns",iconset.path,"-o",output.appendingPathComponent("LumaDock.icns").path];try iconutil.run();iconutil.waitUntilExit();guard iconutil.terminationStatus==0 else {fatalError("iconutil failed")}
// ICO supports PNG entries; write a directory for each scale, including 256px.
func u16(_ x:UInt16)->Data {var n=x.littleEndian;return Data(bytes:&n,count:2)}
func u32(_ x:UInt32)->Data {var n=x.littleEndian;return Data(bytes:&n,count:4)}
let sizes=[16,24,32,48,64,128,256];let images=sizes.map(render)
var ico=Data([0,0,1,0]);ico.append(u16(UInt16(sizes.count)));var offset=6+16*sizes.count
for (size,data) in zip(sizes,images) {ico.append(Data([size==256 ? 0 : UInt8(size),size==256 ? 0 : UInt8(size),0,0]));ico.append(u16(1));ico.append(u16(32));ico.append(u32(UInt32(data.count)));ico.append(u32(UInt32(offset)));offset+=data.count}
for data in images {ico.append(data)}
try ico.write(to:output.appendingPathComponent("LumaDock.ico"))
print("Created original PNG, ICNS and 7-size ICO in Assets/")
