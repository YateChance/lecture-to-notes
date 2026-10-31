"""Read-only source PDF ingestion with explicit physical-page citations."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess
import yaml

def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()

def prepare(root):
    lesson=yaml.safe_load((root/'lesson.yaml').read_text());items=lesson.get('documents',{}).get('sources',[])
    manifest={'schema_version':'1.0','documents':[],'note':'PDF文字层为候选；公式需结合页面图核对。教材和课堂陈述分开。'}
    for item in items:
        identifier=item['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',identifier):raise ValueError('资料id只能包含字母、数字、下划线及短横线')
        original=Path(item['path']).expanduser().resolve()
        if original.suffix.lower()!='.pdf' or not original.is_file():raise ValueError('资料必须为存在的PDF')
        sha=digest(original);target=root/'00_sources/documents'/f'{identifier}.pdf';target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if digest(target)!=sha:raise RuntimeError('归档PDF与来源不同；请使用新的资料id，不覆盖原始资料')
        else:shutil.copy2(original,target)
        folder=root/'05_documents'/identifier;folder.mkdir(parents=True,exist_ok=True)
        info=subprocess.check_output(['pdfinfo',str(target)],text=True)
        match=re.search(r'^Pages:\s+(\d+)',info,re.M)
        if not match:raise RuntimeError('无法读取PDF页数')
        count=int(match.group(1));cache=root/'_runs/documents'/f'{sha}.txt';cache.parent.mkdir(parents=True,exist_ok=True)
        if not cache.exists():subprocess.run(['pdftotext','-layout',str(target),str(cache)],check=True)
        pages=cache.read_text().split('\f');selected=sorted({n for start,end in item.get('pdf_page_ranges',[]) for n in range(start,end+1)})
        images=set(item.get('visual_pages',[]));records=[]
        for page in selected:
            if not 1<=page<=count:raise ValueError(f'{identifier} PDF页码越界: {page}')
            text=folder/f'pdf_{page:04d}.txt';text.write_text(pages[page-1])
            image=folder/f'pdf_{page:04d}.png'
            if page in images and not image.exists():
                subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-scale-to','1800','-singlefile','-png',str(target),str(image.with_suffix(''))],check=True)
            records.append({'document_id':identifier,'pdf_page':page,'printed_page':page-item['printed_page_offset'] if 'printed_page_offset' in item else None,
                            'text':str(text.relative_to(root)),'image':str(image.relative_to(root)) if image.exists() else None,
                            'pdf':str(target.relative_to(root)),'page_id':f'{identifier}_pdf_{page:04d}'})
        document={'id':identifier,'title':item['title'],'role':item.get('role','textbook'),'source_path':str(original),'archive_path':str(target.relative_to(root)),
                  'sha256':sha,'pdf_pages':count,'selected_pages':records,'scope':'selected' if selected else 'catalog_only'}
        manifest['documents'].append(document)
    output=root/'05_documents/documents.json';output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    lines=['# 教材资料索引','','仅引用下列实际页面；页码区分PDF物理页与纸书印刷页。','']
    for document in manifest['documents']:
        lines+=['## '+document['title'],'',f'角色：{document["role"]}；归档PDF：[{document["id"]}](../{document["archive_path"]})。','',
                '| PDF页 | 纸书页 | 文字候选 | 页面图 |','|---:|---:|---|---|']
        for page in document['selected_pages']:
            lines.append(f'| {page["pdf_page"]} | {page["printed_page"] if page["printed_page"] is not None else "未核定"} | [文字]({Path(page["text"]).relative_to("05_documents")}) | '+(f'[页面]({Path(page["image"]).relative_to("05_documents")})' if page['image'] else '未渲染')+' |')
    (root/'05_documents/README.md').write_text('\n'.join(lines)+'\n');return manifest

def context(root):
    manifest=json.loads((root/'05_documents/documents.json').read_text());blocks=[];images=[]
    for document in manifest['documents']:
        blocks.append(f'资料 {document["id"]}：{document["title"]}，角色={document["role"]}。原PDF={document["archive_path"]}；仅登记而未选页的资料不能当作已核来源。')
        for page in document['selected_pages']:
            blocks.append(f'【{page["page_id"]}；PDF物理页{page["pdf_page"]}；印刷页{page["printed_page"]}】\n'+(root/page['text']).read_text())
            if page['image']:images.append(root/page['image'])
    return '\n\n'.join(blocks),images

def ready(root):
    try:
        lesson=yaml.safe_load((root/'lesson.yaml').read_text());items=lesson.get('documents',{}).get('sources',[])
        manifest=json.loads((root/'05_documents/documents.json').read_text())
        docs={doc['id']:doc for doc in manifest['documents']}
        if len(docs)!=len(items) or {item['id'] for item in items}!=set(docs):return False
        for item in items:
            doc=docs[item['id']];archive=root/doc['archive_path']
            if not archive.is_file() or digest(archive)!=doc['sha256']:return False
            source=Path(item['path']).expanduser()
            if source.is_file() and digest(source)!=doc['sha256']:return False
            pages=doc['selected_pages'];selected={n for start,end in item.get('pdf_page_ranges',[]) for n in range(start,end+1)}
            if not selected or len(pages)!=len(selected) or {p['pdf_page'] for p in pages}!=selected:return False
            for page in pages:
                if not (root/page['text']).is_file():return False
                if page['pdf_page'] in item.get('visual_pages',[]) and not page.get('image'):return False
                if page.get('image') and not (root/page['image']).is_file():return False
                if page.get('printed_page')!=(page['pdf_page']-item['printed_page_offset'] if 'printed_page_offset' in item else None):return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False
