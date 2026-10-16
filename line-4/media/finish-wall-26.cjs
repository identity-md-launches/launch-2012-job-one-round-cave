// One-time local assembly of generated pigment over bare inherited stone.
// No network, environment access, or account interaction.
const fs = require('node:fs');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const {decode, encode, thumbnail} = require('../../line-1/media/finish-wall.cjs');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

// Decode the trusted image tool's opaque RGB/RGBA PNG at its native size.
function pigmentPNG(bytes) {
  if (bytes.subarray(0,8).toString('hex') !== '89504e470d0a1a0a') throw Error('PNG required');
  let w, h, channels, parts=[];
  for(let at=8; at<bytes.length;) {
    const n=bytes.readUInt32BE(at), type=bytes.toString('ascii',at+4,at+8);
    const b=bytes.subarray(at+8,at+8+n);
    if(type==='IHDR') {
      w=b.readUInt32BE(0); h=b.readUInt32BE(4); channels=b[9]===2?3:4;
      if(b[8]!==8 || ![2,6].includes(b[9]) || b[12]!==0 || w*h>4194304) throw Error('unsupported tool PNG');
    }
    if(type==='IDAT') parts.push(b);
    at+=n+12;
    if(type==='IEND') break;
  }
  const stride=w*channels, raw=zlib.inflateSync(Buffer.concat(parts),{maxOutputLength:(stride+1)*h});
  if(raw.length!==(stride+1)*h) throw Error('bad PNG length');
  const data=Buffer.alloc(stride*h);
  for(let y=0;y<h;y++) for(let x=0;x<stride;x++) {
    const f=raw[y*(stride+1)], i=y*stride+x;
    if(f>4) throw Error('bad filter');
    const a=x>=channels?data[i-channels]:0, b=y?data[i-stride]:0, c=y&&x>=channels?data[i-stride-channels]:0;
    const p=a+b-c, pa=Math.abs(p-a), pb=Math.abs(p-b), pc=Math.abs(p-c);
    const v=[0,a,b,Math.floor((a+b)/2),pa<=pb&&pa<=pc?a:pb<=pc?b:c][f];
    data[i]=(raw[y*(stride+1)+1+x]+v)&255;
  }
  return {w,h,channels,data};
}

const previous=fs.readFileSync('artifacts/line-4/wall-v6.png');
const generated=fs.readFileSync('artifacts/line-4/wall-v7.png');
const old=decode(previous), pigment=pigmentPNG(generated);
if(pigment.w!==1024 || pigment.h!==1024) throw Error('expected generated 1024px motif');
const out={...old,pixels:Buffer.from(old.pixels)};
const bounds=[886,526,1030,590];
let changed=0, outside=0;
// Crop only the generated twig and pebble. Black is a matte, never painted.
// Flat earth pigments inherit texture from the old stone through the alpha.
for(let y=bounds[1];y<=bounds[3];y++) for(let x=bounds[0];x<=bounds[2];x++) {
  const sx=Math.floor(265+(x-bounds[0])*500/145);
  const sy=Math.floor(475+(y-bounds[1])*220/65);
  const si=(sy*pigment.w+sx)*pigment.channels, di=(y*old.width+x)*3;
  const [r,g,b]=pigment.data.subarray(si,si+3), bright=Math.max(r,g,b);
  if(bright<35) continue;
  const ochre=r>b*1.15, color=ochre?[168,103,43]:[218,193,148];
  const rock=(old.pixels[di]+old.pixels[di+1]+old.pixels[di+2])/3;
  const texture=Math.max(.60,Math.min(1.16,rock/115));
  const wear=((x*47+y*101)%23)/23;
  const alpha=Math.min(.82,(bright-35)/190)*(.55+.45*wear);
  for(let c=0;c<3;c++) out.pixels[di+c]=Math.round(old.pixels[di+c]*(1-alpha)+color[c]*texture*alpha);
}
for(let y=0;y<old.height;y++) for(let x=0;x<old.width;x++) {
  const at=(y*old.width+x)*3;
  if(!old.pixels.subarray(at,at+3).equals(out.pixels.subarray(at,at+3))) {
    changed++;
    if(x<bounds[0]||x>bounds[2]||y<bounds[1]||y>bounds[3]) outside++;
  }
}
if(changed<100 || outside) throw Error('empty mark or preservation failure');
const png=encode(out), jpg=thumbnail(out);
if(!decode(png).pixels.equals(out.pixels) || jpg.length>100000) throw Error('output check failed');
fs.writeFileSync('artifacts/line-4/wall-v7.png',png);
// Never follow an inherited canonical symlink into an older wall.
try { fs.unlinkSync('artifacts/line-4/wall.png'); } catch(e) { if(e.code!=='ENOENT') throw e; }
fs.linkSync('artifacts/line-4/wall-v7.png','artifacts/line-4/wall.png');
fs.writeFileSync('artifacts/line-4/26.jpg',jpg);
fs.linkSync('artifacts/line-4/26.jpg','dist/line-4/26.jpg');
const report={source:'artifacts/line-4/wall-v6.png',source_sha256:sha(previous),
  generated_sha256:sha(generated),wall:'artifacts/line-4/wall-v7.png',sha256:sha(png),
  width:out.width,height:out.height,format:'PNG',bytes:png.length,
  preview:'dist/line-4/26.jpg',preview_width:512,preview_height:512,preview_format:'JPEG',preview_bytes:jpg.length,
  addition_bounds_inclusive:bounds,changed_pixels:changed,changed_pixels_outside_addition:outside,
  png_roundtrip_passed:true};
fs.writeFileSync('line-4/media-check-26.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
