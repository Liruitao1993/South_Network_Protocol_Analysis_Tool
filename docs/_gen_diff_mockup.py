import pathlib

C = ":root{--green:#4CAF50;--blue:#2196F3;--orange:#FF9800;--gray:#9e9e9e;--txt:#222;--muted:#666;--faint:#999;--border:#dcdcdc;--head:#f0f0f0;--alt:#fafafa;--panel:#f7f7f7;--same:#f5f5f5;--st:#888;--mod:#ffebee;--mt:#c62828;--mb:#ef9a9a;--add:#fff8e1;--at:#b06800;--ab:#ffe082;--del:#eceff1;--dt:#90a4ae}"
S = "*{box-sizing:border-box}body{margin:0;font-family:'Microsoft YaHei','SimSun',sans-serif;font-size:12px;color:var(--txt);background:#cfd8dc}"
H = ".win{width:1180px;margin:18px auto;background:#fff;border:1px solid #b0bec5;border-radius:6px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.18)}"
T = ".tbar{height:30px;background:#37474f;color:#eceff1;display:flex;align-items:center;padding:0 12px}.tbar .d{display:flex;gap:7px;margin-right:14px}.tbar .d i{width:11px;height:11px;border-radius:50%;display:inline-block}.r{background:#ff5f56}.y{background:#ffbd2e}.g{background:#27c93f}"
M = ".mbar{height:26px;background:#eceff1;border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 8px;gap:18px;color:#333}.mbar .p{margin-left:auto;display:flex;align-items:center;gap:6px;color:var(--muted)}.mbar select{font-size:12px;padding:1px 4px}"
TB = ".tabs{display:flex;background:#eceff1;border-bottom:1px solid var(--border);padding:0 6px}.tb{padding:7px 16px;border:1px solid transparent;border-bottom:none;color:var(--muted);margin-right:2px;border-radius:4px 4px 0 0}.tb.a{background:#fff;color:var(--blue);border-color:var(--border);font-weight:600}.tb.a .n{font-size:9px;background:var(--orange);color:#fff;border-radius:3px;padding:1px 4px;margin-left:6px;font-weight:700}"
TL = ".tlbar{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border);background:#fff;flex-wrap:wrap}.tlbar .t{font-weight:600;color:#333;font-size:13px;margin-right:10px}.btn{border:none;border-radius:3px;padding:5px 13px;color:#fff;font-size:12px}.btn.gr{background:var(--green)}.btn.bl{background:var(--blue)}.btn.or{background:var(--orange)}.btn.gy{background:var(--gray)}.btn.ol{background:#fff;color:var(--muted);border:1px solid var(--border)}.sp{flex:1}"
IN = ".ins{display:flex;gap:10px;padding:10px 12px;background:var(--panel);border-bottom:1px solid var(--border)}.ib{flex:1;border:1px solid var(--border);background:#fff;border-radius:4px;overflow:hidden}.ih{display:flex;align-items:center;justify-content:space-between;padding:5px 10px;background:var(--head);border-bottom:1px solid var(--border);color:var(--muted)}.ih b{color:#333}.bdg{font-size:11px;color:var(--faint)}.ibd{font-family:Consolas,monospace;font-size:12.5px;padding:9px 10px;line-height:1.7;letter-spacing:.5px;word-break:break-all}.ibd .mk{background:var(--mod);color:var(--mt);border-radius:2px;padding:1px 2px;font-weight:700}"
SM = ".sm{display:flex;align-items:center;gap:14px;padding:8px 12px;border-bottom:1px solid var(--border);background:#fff;flex-wrap:wrap}.ch{padding:3px 9px;border-radius:10px;font-size:11.5px}.ch.al{background:#e3f2fd;color:#1565c0}.ch.mo{background:var(--mod);color:var(--mt)}.ch.ad{background:var(--add);color:var(--at)}.ch.de{background:var(--del);color:var(--dt)}.sm .o{margin-left:auto;display:flex;gap:14px;color:var(--muted)}.cb{width:13px;height:13px;border:1.5px solid #bdbdbd;border-radius:2px;display:inline-block;position:relative;background:#fff}.cb.on{background:var(--blue);border-color:var(--blue)}.cb.on::after{content:'';position:absolute;left:3px;top:0;width:4px;height:8px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}"
SC = ".sec{padding:10px 12px}.sti{font-weight:600;color:#333;font-size:12.5px;margin:0 0 7px;display:flex;align-items:center;gap:8px}.sti .h{font-weight:400;color:var(--faint);font-size:11px}"
BW = ".bwr{border:1px solid var(--border);border-radius:4px;overflow:hidden}.br{display:flex;align-items:stretch;border-bottom:1px solid #f0f0f0}.br:last-child{border-bottom:none}.br .fn{width:96px;flex:none;background:var(--head);color:var(--muted);display:flex;align-items:center;padding:0 10px;font-size:11.5px;border-right:1px solid var(--border)}.br .sd{flex:1;padding:5px 10px;font-family:Consolas,monospace;font-size:12.5px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}.br .sd.l{border-right:1px solid #f0f0f0}.by{display:inline-block;min-width:22px;text-align:center;padding:2px 4px;border-radius:3px;background:var(--same);color:var(--st)}.by.mo{background:var(--mod);color:var(--mt);font-weight:700;outline:1px solid var(--mb)}.by.ad{background:var(--add);color:var(--at);font-weight:700;outline:1px solid var(--ab)}.gp{display:inline-block;min-width:22px;text-align:center;color:var(--faint);padding:2px 4px}"
TB2 = "table.sm2{width:100%;border-collapse:collapse;font-size:12px}table.sm2 th,table.sm2 td{border:1px solid var(--border);padding:5px 8px;text-align:left}table.sm2 th{background:var(--head);color:#444;font-weight:600}table.sm2 td.m{font-family:Consolas,monospace}table.sm2 tr.al td{background:var(--alt)}.tg{display:inline-block;padding:1px 7px;border-radius:8px;font-size:11px}.tg.s{background:#eceff1;color:#607d8b}.tg.m{background:var(--mod);color:var(--mt);font-weight:600}.tg.a{background:var(--add);color:var(--at);font-weight:600}"
NT = ".nt{border:1px solid var(--border);border-left:3px solid var(--orange);border-radius:4px;background:#fffdf5;padding:9px 12px}.nt li{margin:3px 0;line-height:1.6}.nt code{font-family:Consolas,monospace;background:#f5f5f5;padding:0 4px;border-radius:2px;color:var(--mt)}.lg{display:flex;gap:14px;color:var(--muted);font-size:11px;align-items:center}.sw{display:inline-block;width:13px;height:13px;border-radius:2px;margin-right:4px;vertical-align:middle}"
print("CSS parts ready")
print("CSS parts ready")
css = "<style>" + C + S + H + T + M + TB + TL + IN + SM + SC + BW + TB2 + NT + "</style>"
def by(v, cls=""):
    c = ' class="by %s"' % cls if cls else ' class="by"'
    return '<span%s>%s</span>' % (c, v)
def row(fn, left, right):
    return '<div class="br"><div class="fn">%s</div><div class="sd l">%s</div><div class="sd">%s</div></div>' % (fn, left, right)
def bseq(vals):
    return "".join(by(v, c) for v, c in vals)
print("body funcs ready")
print("body funcs ready")
head = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>报文对比 Diff</title>'
head += css + '</head><body><div class="win">'
titlebar = '<div class="tbar"><div class="d"><i class="r"></i><i class="y"></i><i class="g"></i></div>南网协议解析工具 v1.7.2 — 报文对比</div>'
menubar = '<div class="mbar"><span>配置(&amp;C)</span><span>帮助(&amp;H)</span><div class="p">协议：<select><option>南网协议 (Q/CSG1209021-2019)</option></select></div></div>'
tabs = '<div class="tabs"><div class="tb">单帧解析</div><div class="tb">查询</div><div class="tb">批量解析</div><div class="tb">协议组帧</div><div class="tb">预设命令</div><div class="tb">测试方案</div><div class="tb">档案管理</div><div class="tb">拓扑信息</div><div class="tb a">报文对比<span class="n">NEW</span></div></div>'
toolbar = '<div class="tlbar"><span class="t">报文对比 Diff</span><button class="btn gr">开始对比</button><button class="btn ol">交换 A\u2194B</button><button class="btn ol">从单帧解析载入 A</button><button class="btn ol">从单帧解析载入 B</button><div class="sp"></div>'
toolbar += '<div class="lg"><span><i class="sw" style="background:var(--same)"></i>相同</span><span><i class="sw" style="background:var(--mod)"></i>修改</span><span><i class="sw" style="background:var(--add)"></i>B新增</span></div>'
toolbar += '<button class="btn gy">导出对比报告</button></div>'
print("chrome ready")
print("chrome ready")
inpA = '68 <span class="mk">14</span> 00 <span class="mk">14</span> 00 <span class="mk">4D</span> 01 01 E8 03 03 74 00 00 02 00 <span class="mk">7B</span> 16'
inpB = '68 <span class="mk">16</span> 00 <span class="mk">16</span> 00 <span class="mk">8D</span> 01 01 E8 03 03 74 00 00 02 00 <span class="mk">9A 8C</span> 16'
inputs = '<div class="ins"><div class="ib"><div class="ih"><b>报文 A（基准）</b><span class="bdg">18 字节 \u00b7 请求帧</span></div><div class="ibd">%s</div></div>' % inpA
inputs += '<div class="ib"><div class="ih"><b>报文 B（对比）</b><span class="bdg">19 字节 \u00b7 响应帧</span></div><div class="ibd">%s</div></div></div>' % inpB
summary = '<div class="sm"><span class="ch al">A: 18 字节 / B: 19 字节</span><span class="ch mo">修改 3 处</span><span class="ch ad">B 新增 1 字节</span><span class="ch de">A 独有 0</span>'
summary += '<div class="o"><label><span class="cb on"></span>字段感知对齐</label><label><span class="cb"></span>忽略校验和字节</label><label><span class="cb"></span>忽略序列号</label><label><span class="cb"></span>仅显示差异</label></div></div>'
print("inputs ready")
print("inputs ready")
sec1 = '<div class="sec"><div class="sti">字节级对比（按字段对齐）<span class="h">\u2014 协议感知：长度不同的帧也能把“校验和”对“校验和”、“结束符”对“结束符”</span></div><div class="bwr">'
sec1 += row("起始符", by("68"), by("68"))
sec1 += row("长度域", bseq([("14","mo"),("00",""),("14","mo"),("00","")]), bseq([("16","mo"),("00",""),("16","mo"),("00","")]))
sec1 += row("控制域", by("4D","mo"), by("8D","mo"))
sec1 += row("地址域", bseq([("01",""),("01","")]), bseq([("01",""),("01","")]))
sec1 += row("AFN", by("E8"), by("E8"))
sec1 += row("DI", bseq([("03",""),("03",""),("74",""),("00","")]), bseq([("03",""),("03",""),("74",""),("00","")]))
sec1 += row("序列号", bseq([("00",""),("00","")]), bseq([("00",""),("00","")]))
sec1 += row("数据内容", bseq([("02",""),("00","")]) + '<span class="gp">\u2014</span>', bseq([("02",""),("00",""),("9A","ad")]))
sec1 += row("校验和", by("7B","mo"), by("8C","mo"))
sec1 += row("结束符", by("16"), by("16"))
sec1 += '</div></div>'
print("byte section ready")
print("byte section ready")
def tr(cells, alt=False):
    return "<tr%s>%s</tr>" % (' class="al"' if alt else "", "".join("<td%s>%s</td>" % (' class="m"' if c[0] else "", c[1]) for c in cells))
def th(labels):
    return "<tr>" + "".join("<th>%s</th>" % l for l in labels) + "</tr>"
sec2 = '<div class="sec"><div class="sti">字段级语义对比<span class="h">\u2014 直接告诉你“哪个字段的含义变了”，而不只是看字节</span></div>'
sec2 += '<table class="sm2"><thead>' + th(["字段","偏移","长度","报文 A","报文 B","差异"]) + '</thead><tbody>'
sec2 += tr([("","起始符"),(1,"0"),(1,"1"),(1,"68"),(1,"68"),("",'<span class="tg s">相同</span>')])
sec2 += tr([("","长度域"),(1,"1"),(1,"4"),(1,"14 00 14 00 (20)"),(1,"16 00 16 00 (22)"),("",'<span class="tg m">修改</span>')], True)
sec2 += tr([("","控制域"),(1,"3"),(1,"1"),(1,"4D（PRM=1 请求·序号1）"),(1,"8D（PRM=0 响应·序号1）"),("",'<span class="tg m">修改</span>')])
sec2 += tr([("","地址域"),(1,"4"),(1,"2"),(1,"01 01"),(1,"01 01"),("",'<span class="tg s">相同</span>')], True)
sec2 += tr([("","AFN"),(1,"6"),(1,"1"),(1,"E8（查询运行参数）"),(1,"E8（查询运行参数）"),("",'<span class="tg s">相同</span>')])
sec2 += tr([("","DI"),(1,"7"),(1,"4"),(1,"03 03 74 00"),(1,"03 03 74 00"),("",'<span class="tg s">相同</span>')], True)
sec2 += tr([("","数据内容"),(1,"11"),(1,"2"),(1,"02 00"),(1,"02 00 9A"),("",'<span class="tg a">B新增1字节</span>')])
sec2 += tr([("","校验和"),(1,"16"),(1,"1"),(1,"7B"),(1,"8C"),("",'<span class="tg m">修改</span>')], True)
sec2 += tr([("","结束符"),(1,"17"),(1,"1"),(1,"16"),(1,"16"),("",'<span class="tg s">相同</span>')])
sec2 += '</tbody></table></div>'
print("table section ready")
print("table section ready")
sec3 = '<div class="sec"><div class="sti">差异说明（人话解读）</div><div class="nt"><ul>'
sec3 += '<li>长度域：<code>0x14(20)</code> \u2192 <code>0x16(22)</code>，B 比 A 多 2 字节（响应数据多 1 字节 + 校验和前移）</li>'
sec3 += '<li>控制域：<code>0x4D</code> \u2192 <code>0x8D</code>，PRM 位 1\u21920（请求帧\u2192响应帧），方向反转，其余位不变</li>'
sec3 += '<li>数据内容：B 在偏移 11 处新增字节 <code>9A</code>（响应携带的运行参数值）</li>'
sec3 += '<li>校验和：<code>0x7B</code> \u2192 <code>0x8C</code>，因内容变化后自动重算（如勾选“忽略校验和字节”则此项不显示）</li>'
sec3 += '</ul></div></div>'
foot = '</div></body></html>'
html = head + titlebar + menubar + tabs + toolbar + inputs + summary + sec1 + sec2 + sec3 + foot
p = pathlib.Path(__file__).parent / "diff_mockup.html"
p.write_text(html, encoding="utf-8")
print("wrote", p, len(html), "bytes")
