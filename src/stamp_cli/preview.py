"""An offline, synthetic style gallery rendered with the actual export engine."""
from __future__ import annotations

import base64
import html
import shlex

from .core import export, raster
from .examples import SAMPLES


def gallery(specs):
    cards, errors = [], []
    for spec in specs:
        variants = [(spec.META.title, dict(SAMPLES.get(spec.META.id, {})), None)]
        if spec.META.id == "esign.signature":
            variants = [("Framed signature", {"signature": "typed", "name": "Alex Morgan", "font": "sans"}, "classic"),
                        ("Clean signature", {"signature": "typed", "name": "Alex Morgan", "font": "sans", "label": "Signature", "color": "#242A30", "show_id": False}, "clean"),
                        ("Signature only", {"signature": "typed", "name": "Alex Morgan", "color": "#242A30"}, "signature-only")]
        for title, params, layout in variants:
            if layout:
                params["layout"] = layout
            try:
                result = spec.build_svg(**params)
                mm, height, pixels, dpi = export.dimensions(result, dpi=300)
                source = export.prepare_svg(result, width_mm=mm, height_mm=height)
                png = raster.render_png(source, font_files=[fp.file_path for fp in result.fonts_used],
                                        width=pixels, skip_system_fonts=True)
                image = base64.b64encode(png).decode("ascii")
                command = (f'stamp sign --name "Alex Morgan" --layout {layout} -o signature.png'
                           if layout else ' '.join(['stamp', *spec.META.id.replace('_', '-').split('.'),
                           *[token for key, value in params.items() for token in
                             ['--' + key.replace('_', '-'), shlex.quote(str(value))]], '-o', 'seal.png']))
                if layout == "clean":
                    command += ' --no-show-id --color "#242A30" --label Signature'
                cards.append(f'<article data-search="{html.escape(title + " " + spec.META.id, quote=True)}">'
                             f'<div class="paper"><img alt="{html.escape(title, quote=True)}" '
                             f'style="--width:{mm:g}mm" src="data:image/png;base64,{image}"></div>'
                             f'<div class="caption"><h2>{html.escape(title)}</h2>'
                             f'<p>{mm:g} × {height:.1f} mm · {html.escape(spec.META.id)}</p>'
                             f'<code>{html.escape(command)}</code></div></article>')
            except Exception as e:
                errors.append({"style": spec.META.id, "error": str(e)})
                cards.append(f'<article data-search="{html.escape(title, quote=True)}"><div class="caption">'
                             f'<h2>{html.escape(title)}</h2><p class="missing">Preview unavailable</p>'
                             '<p>Run <code>stamp doctor</code> to check fonts and rendering.</p></div></article>')
    page = _HEAD + ''.join(cards) + _TAIL
    return page, errors


_HEAD = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stamp — style library</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f5f3;color:#242A30;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1260px;margin:auto;padding:58px 36px}header{margin-bottom:30px}h1{font-size:36px;line-height:1.2;font-weight:550;letter-spacing:-1.2px;margin:0 0 14px}header p{max-width:680px;color:#5e6367;margin:8px 0}
.controls{display:flex;gap:16px;align-items:center;justify-content:space-between;margin:30px 0 24px;flex-wrap:wrap}input{font:inherit;background:#fff;border:1px solid #d6d9d8;border-radius:7px;padding:10px 14px;width:340px;max-width:100%}button{font:inherit;font-size:13px;background:white;border:1px solid #c5caca;border-radius:5px;padding:7px 11px;cursor:pointer}button[aria-pressed=true]{background:#242A30;color:white;border-color:#242A30}button:focus-visible,input:focus{outline:2px solid #798989;outline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}article{border:1px solid #e2e3df;background:#fff;border-radius:10px;overflow:hidden;min-width:0}article[hidden]{display:none}.paper{min-height:230px;display:flex;align-items:center;justify-content:center;padding:30px 24px;border-bottom:1px solid #edeeea;overflow:auto}img{width:calc(var(--width)*var(--zoom,1));height:auto;max-width:none;flex-shrink:0}.caption{padding:19px 24px 22px}h2{font-size:16px;font-weight:600;margin:0 0 5px}.caption p{font-size:12px;color:#72787c;margin:0 0 12px}code{font:11px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:normal;word-break:normal;white-space:pre;display:block;overflow-x:auto;color:#575e62}.missing{color:#97593b!important}footer{padding-top:32px;color:#71777a;font-size:12px}#empty{color:#676d70}
@media(max-width:760px){main{padding:30px 18px}.grid{grid-template-columns:1fr}h1{font-size:30px}.paper{justify-content:flex-start;min-height:200px}}
@media print{body{background:white}main{padding:0}.controls{display:none}.grid{display:block}article{break-inside:avoid;margin-bottom:16px}.paper{--zoom:1}}
</style><main><header><h1>Every mark, considered.</h1><p>Signature graphics, company seals and office stamps. Choose a style, then use its command to make it yours.</p><p>All examples are fictional. Previews use the same fonts and rendering engine as your exports.</p></header>
<div class="controls"><input id="search" type="search" placeholder="Find a signature, oval, office stamp…" aria-label="Filter styles"><div aria-label="Preview scale"><button data-zoom="1" aria-pressed="true">Print proportions</button> <button data-zoom="1.5" aria-pressed="false">Enlarge 150%</button></div></div>
<div class="grid">'''

_TAIL = '''</div><p id="empty" hidden>No matching styles. Try another search.</p>
<footer>Screen size varies by display and browser zoom. Exported millimetres and PNG resolution are authoritative.<br>Signature references identify graphics. These images do not create a cryptographic PDF signature or authenticate a signer.</footer></main>
<script>
const search=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];
search.addEventListener('input',()=>{const words=search.value.toLowerCase().trim().split(/\\s+/);let count=0;cards.forEach(card=>{card.hidden=!words.every(word=>card.dataset.search.toLowerCase().includes(word));if(!card.hidden)count++});document.querySelector('#empty').hidden=count>0});
document.querySelectorAll('[data-zoom]').forEach(button=>button.addEventListener('click',()=>{document.documentElement.style.setProperty('--zoom',button.dataset.zoom);document.querySelectorAll('[data-zoom]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)))}));
</script></html>'''
