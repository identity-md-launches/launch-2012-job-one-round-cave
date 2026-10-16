// Build-time preservation pass over the image tool's additive painting.
// Reads only workspace image assets; writes only the wall and its thumbnail.
const fs = require('node:fs');
const crypto = require('node:crypto');
const media = require('../line-1/media/finish-wall.cjs');
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const destination = 'artifacts/gathering/wall-v7.png';
const oldBytes = fs.readFileSync('artifacts/gathering/wall-v6.png');
const generatedBytes = fs.readFileSync(destination);
if(hash(generatedBytes)!=='7c8cec7692501b9d60dcc3f921d0550b5f5756d1b6f1888e8eb365d9fb6167c8') throw Error('Requires original reviewed generation; do not rerun on final wall');
const old = media.decode(oldBytes), generated = media.decode(generatedBytes);
const output = {...old, pixels: Buffer.from(old.pixels)};
// This small patch was visually checked to contain bare rock, no ancestor pigment.
const box = [225, 322, 100, 160];
const segments = [[236,331,301,469],[311,332,249,475],
                  [230,364,252,378],[254,335,245,353],
                  [319,369,293,383],[303,350,292,362]];
function distance(x,y,[ax,ay,bx,by]) {
  const t = Math.max(0,Math.min(1,((x-ax)*(bx-ax)+(y-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)));
  return Math.hypot(x-ax-t*(bx-ax), y-ay-t*(by-ay));
}
let changed = 0;
for (let y=box[1]; y<box[1]+box[3]; y++) for(let x=box[0]; x<box[0]+box[2]; x++) {
  const i=(y*old.width+x)*3;
  const [r,g,b]=generated.pixels.subarray(i,i+3);
  const binding=x>=258 && x<=285 && y>=407 && y<=440 && r>g*1.55 && r-b>40;
  const branch=segments.some(s=>distance(x,y,s)<7) && r<105 && g<85 && b<65;
  if(!binding && !branch) continue;
  const color=binding ? [155,62,29] : [43,36,25];
  // Preserve the original texture and illumination through semi-opaque pigment.
  const alpha=binding ? Math.min(.78,(r-g)/110) : Math.min(.85,(135-r)/100);
  for(let c=0;c<3;c++) output.pixels[i+c]=Math.round(old.pixels[i+c]*(1-alpha)+color[c]*alpha);
  if(!old.pixels.subarray(i,i+3).equals(output.pixels.subarray(i,i+3))) changed++;
}
if(changed<1000) throw Error('mark missing');
const protectedHash=crypto.createHash('sha256'); let outside=0;
for(let y=0;y<old.height;y++) for(let x=0;x<old.width;x++) {
  if(x>=box[0] && x<box[0]+box[2] && y>=box[1] && y<box[1]+box[3]) continue;
  const i=(y*old.width+x)*3, a=old.pixels.subarray(i,i+3), b=output.pixels.subarray(i,i+3);
  if(!a.equals(b)) outside++;
  protectedHash.update(b);
}
if(outside) throw Error('inherited pixel changed outside mark');
const bytes=media.encode(output), preview=media.thumbnail(output);
if(!media.decode(bytes).pixels.equals(output.pixels) || preview.length>100000) throw Error('encoding check failed');
fs.writeFileSync(destination,bytes);
fs.writeFileSync('dist/gathering/26.jpg',preview);
fs.unlinkSync('artifacts/gathering/wall.png');
fs.symlinkSync('wall-v7.png','artifacts/gathering/wall.png');
const report={inherited_wall_sha256:hash(oldBytes), generated_edit_sha256:hash(generatedBytes),output_sha256:hash(bytes),
  mark_rectangle:box,changed_pixels_inside:changed,pixels_changed_outside:outside,protected_rgb_sha256:protectedHash.digest('hex'),
  method:'Image-tool branch and binding pigment selected within a bare-rock patch and composited over original rock. All other RGB pixels retained.',
  png_dimensions:[old.width,old.height],png_format:'RGB PNG',jpeg_dimensions:[512,512],jpeg_bytes:preview.length};
fs.writeFileSync('gathering/preservation-26.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
