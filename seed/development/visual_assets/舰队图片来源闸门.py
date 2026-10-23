#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External-only image resolver. Does not bundle images in save; original ZIP must be provided independently."""
from pathlib import Path
import argparse,os,json,hashlib,zipfile,re,sys
HERE=Path(__file__).resolve().parent
INDEX=HERE/'image_source_index.json'
PACKAGES=('vehicle_posters_en.zip','combat_robot_posters_en.zip','space_uav_posters_en.zip','armored_vehicle_posters_en.zip','combat_uav_armored_images_en.zip')

def digest(x):return hashlib.sha256(x).hexdigest()
def load_index():
 d=json.loads(INDEX.read_text('utf-8'))
 if d.get('schema')!='VOYAGER_EXTERNAL_IMAGE_INDEX_V1' or d.get('image_storage')!='EXTERNAL_PROJECT_SOURCES_ONLY':raise ValueError('无效外部图片索引')
 if set(d['source_zip_sha256'])!=set(PACKAGES) or len(d['assets'])!=20:raise ValueError('外部图片包清单不完整')
 if any(v['archive'] not in PACKAGES for v in d['assets'].values()):raise ValueError('索引含未知图包')
 if any(v not in d['assets'] for v in d['aliases'].values()):raise ValueError('中文别名未指向索引图片')
 return d

def roots(explicit=None):
 paths=[explicit,os.environ.get('VOYAGER_IMAGE_SOURCE_DIR'),os.environ.get('VOYAGER_PROJECT_SOURCE_DIR'),'/mnt/data',os.getcwd(),os.path.join(os.getcwd(),'来源')]
 p=HERE
 for _ in range(5):
  paths.extend((str(p),str(p/'来源')));p=p.parent
 seen=set()
 for path in paths:
  if not path:continue
  d=Path(path).expanduser().resolve()
  if d not in seen:seen.add(d);yield d

def source_dir(index,explicit=None):
 for d in roots(explicit):
  if all((d/n).is_file() for n in PACKAGES):return d
 raise FileNotFoundError('未发现项目来源中的五个原始图片ZIP；禁止生成替代图。请单独提供图片ZIP，或指定--root/VOYAGER_IMAGE_SOURCE_DIR。')

def member_bytes(root,index,name):
 info=index['assets'][name];pkg=root/info['archive']
 if digest(pkg.read_bytes())!=index['source_zip_sha256'][info['archive']]:raise ValueError('来源ZIP整体哈希不符：'+info['archive'])
 with zipfile.ZipFile(pkg) as z:raw=z.read(info['member'])
 if digest(raw)!=info['sha256'] or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('来源PNG校验失败：'+name)
 return raw

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',default=None,help='外部原始图片ZIP所在目录')
 sub=p.add_subparsers(dest='mode',required=True)
 for q in ('index-check','verify-all','list'):sub.add_parser(q)
 rr=sub.add_parser('resolve');rr.add_argument('label')
 aa=sub.add_parser('audit');aa.add_argument('--required',nargs='+',required=True);aa.add_argument('--text-file',required=True,type=Path)
 a=p.parse_args()
 try:
  index=load_index()
  if a.mode=='index-check':out={'status':'PASS','index_records':len(index['assets']),'source_archives':len(PACKAGES),'original_images_embedded':0}
  elif a.mode=='list':out={'status':'PASS','aliases':index['aliases'],'unique_files':len(index['assets'])}
  else:
   root=source_dir(index,a.root)
   if a.mode=='verify-all':
    for n in PACKAGES:
     if digest((root/n).read_bytes())!=index['source_zip_sha256'][n]:raise ValueError('来源ZIP整体哈希错误：'+n)
    for name in index['assets']:member_bytes(root,index,name)
    with zipfile.ZipFile(root/'combat_uav_armored_images_en.zip') as z:
     for name in z.namelist():
      if name not in index['assets'] or digest(z.read(name))!=index['assets'][name]['sha256']:raise ValueError('复合包图片校验失败：'+name)
    out={'status':'PASS','verified_unique_images':len(index['assets']),'source_archives':len(PACKAGES),'original_images_embedded':0}
   elif a.mode=='resolve':
    fn=index['aliases'].get(a.label,a.label)
    if fn not in index['assets']:raise ValueError('未登记的图像名称：'+a.label)
    data=member_bytes(root,index,fn)
    output=root/'verified_game_images'/fn;output.parent.mkdir(parents=True,exist_ok=True)
    if not output.exists() or digest(output.read_bytes())!=index['assets'][fn]['sha256']:output.write_bytes(data)
    out={'status':'PASS','label':a.label,'source_zip':index['assets'][fn]['archive'],'member':fn,'sha256':index['assets'][fn]['sha256'],'verified_path':str(output),'markdown':'!['+a.label+'](sandbox:'+str(output)+')'}
   else:
    draft=a.text_file.read_text('utf-8')
    if re.search(r'<AsyncImage\b[^>]*\b(?:query|src)\s*=',draft,re.I):raise ValueError('禁止使用检索图片或远程图片替代原图')
    links=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',draft);seen=set()
    for lnk in links:
     path=lnk.split(' ',1)[0]
     if not path.startswith('sandbox:/mnt/data/verified_game_images/'):raise ValueError('图片非已验证原图：'+path)
     fp=Path(path[len('sandbox:'):]);name=fp.name
     if name not in index['assets'] or not fp.is_file() or digest(fp.read_bytes())!=index['assets'][name]['sha256']:raise ValueError('原图哈希失败：'+path)
     seen.add(name)
    for label in a.required:
     name=index['aliases'].get(label,label)
     if name not in seen:raise ValueError('缺少本次请求的原图：'+label)
    out={'status':'PASS','verified_images_in_reply':len(seen)}
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except Exception as e:
  print(json.dumps({'status':'BLOCK','error':str(e),'policy':'停止贴图，不生成或检索替代图'},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
