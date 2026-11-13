"""Generate editable diagrams.net wireframes, SVG previews, and PlantUML sources.

All examples are fictional. This is a design deliverable, not a backend implementation.
"""
from pathlib import Path
import json
import html
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = Path(__file__).resolve().parent / "ui"
CONFIG = json.loads((Path(__file__).with_name('design.json')).read_text(encoding='utf-8'))
PRIMARY = CONFIG['primary']
INK, MUTED, BORDER, BG = '#142D4E', '#63748A', '#DCE4EE', '#F4F7FB'
BLUE_BG, RED, RED_BG = '#EAF2FE', '#A3353B', '#FFF1F0'

class Canvas:
    def __init__(self, name, title, subtitle, admin=False, selected='商品集市'):
        subtitle=re.sub(r'^M\d\s*/\s*M\d\s*·\s*','',subtitle)
        subtitle=re.sub(r'^M\d(?:\s*/\s*M\d)?\s+[^/]+/\s*','',subtitle)
        self.name, self.title, self.subtitle = name, title, subtitle
        self.e = []
        self.rect(0,0,1366,768,BG)
        self.rect(0,0,202,768,'#102B4D')
        self.text(28,29,'校 园 闲 置',24,'#FFFFFF',True)
        self.text(28,66,'CAMPUS / SECOND HAND',10,'#A4B8D0')
        auth=name.startswith('01_')
        nav = ['审核工作台','违规处理','平台统计','审计日志','隐私访问'] if admin else (['商品集市','登录 / 注册'] if auth else ['商品集市','我的商品','我的预约','卖家工作台','成交统计','业务历史'])
        for i,label in enumerate(nav):
            y=127+i*56
            if label==selected:
                self.rect(16,y-8,170,44,'#274F7C',radius=7)
                self.rect(16,y,3,27,'#70A7FF')
            self.text(34,y,label,16,'#FFFFFF' if label==selected else '#B8C8DB',label==selected)
        self.text(25,654,'游客 / 登录后可交易' if auth else ('管理端 / 独立账号' if admin else '普通账号 / 可买可卖'),13,'#B8C8DB')
        self.text(25,684,'未进行在校身份核验' if auth else ('示例用户：admin' if admin else '示例用户：lin_24'),13,'#B8C8DB')
        self.text(25,719,'返回集市' if auth else '退出登录',14,'#FFFFFF')
        self.rect(202,0,1164,70,'#FFFFFF')
        self.text(238,25,'校园二手交易系统',16,INK,True)
        self.text(1015,27,'管理端' if admin else '桌面网页 · 设计原型',13,MUTED)
        self.text(1210,26,'游客' if auth else ('admin' if admin else 'lin_24'),14,INK)
        self.text(238,98,title,28,INK,True)
        self.text(239,141,subtitle,14,MUTED)
        self.text(238,739,f'{name[:2]} / {title}',11,MUTED)
        self.text(1080,739,'示例数据 · 1366 × 768',11,MUTED)
    def rect(self,x,y,w,h,fill='#FFFFFF',stroke=None,radius=0):
        self.e.append(dict(kind='rect',x=x,y=y,w=w,h=h,fill=fill,stroke=stroke,radius=radius))
    def text(self,x,y,t,size=15,color=INK,bold=False):
        self.e.append(dict(kind='text',x=x,y=y,w=0,h=size+6,text=t,size=size,color=color,bold=bold))
    def lines(self,x,y,items,size=15,color=INK,step=28):
        for i,t in enumerate(items): self.text(x,y+i*step,t,size,color)
    def card(self,x,y,w,h): self.rect(x,y,w,h,'#FFFFFF',BORDER,10)
    def button(self,x,y,label,w=132,primary=True,danger=False):
        color=RED if danger else PRIMARY
        self.rect(x,y,w,40,color if primary else '#FFFFFF',None if primary else BORDER,6)
        self.text(x+16,y+10,label,14,'#FFFFFF' if primary else color,True)
    def tag(self,x,y,t,color=PRIMARY,bg=BLUE_BG,w=None):
        w=w or max(68,len(t)*14+20)
        self.rect(x,y,w,27,bg,None,5); self.text(x+10,y+5,t,12,color,True)
    def field(self,x,y,label,value,w=360,error=None):
        self.text(x,y,label,14,INK,True)
        self.rect(x,y+27,w,43,'#FFFFFF',RED if error else BORDER,5)
        self.text(x+13,y+40,value,14,MUTED)
        if error:self.text(x,y+76,error,12,RED)
    def banner(self,x,y,w,lines,kind='info'):
        self.rect(x,y,w,24+len(lines)*24,RED_BG if kind=='error' else BLUE_BG,None,7)
        for i,t in enumerate(lines):self.text(x+16,y+13+i*24,t,13,RED if kind=='error' else PRIMARY)
    def table(self,x,y,width,headers,rows,colwidths=None,rowh=60):
        if colwidths is None: colwidths=[width//len(headers)]*len(headers)
        self.rect(x,y,width,42,'#EDF2F8',None,4)
        for i,t in enumerate(headers):self.text(x+sum(colwidths[:i])+14,y+13,t,13,MUTED,True)
        for r,row in enumerate(rows):
            yy=y+42+r*rowh
            self.rect(x,yy,width,rowh,'#FFFFFF')
            self.rect(x,yy+rowh-1,width,1,BORDER)
            for i,t in enumerate(row):self.text(x+sum(colwidths[:i])+14,yy+20,t,13,PRIMARY if i==len(row)-1 else INK)
    def tabs(self,x,y,labels,active=0,gap=145):
        for i,t in enumerate(labels):
            self.text(x+i*gap,y,t,14,PRIMARY if i==active else MUTED,i==active)
            if i==active:self.rect(x+i*gap,y+28,100,3,PRIMARY)
    def art(self,x,y,w,h,kind):
        self.rect(x,y,w,h,'#EAF0F8',None,7)
        if kind=='book':
            self.rect(x+w*.27,y+h*.16,w*.45,h*.65,'#456C9C',None,5)
            self.rect(x+w*.3,y+h*.16,4,h*.65,'#91B7E0')
            self.text(x+w*.33,y+h*.32,'软件工程',max(13,int(w*.07)),'#FFFFFF',True)
            self.text(x+w*.33,y+h*.52,'第 4 版',max(10,int(w*.05)),'#C6D8EE')
        elif kind=='lamp':
            self.rect(x+w*.47,y+h*.25,9,h*.49,'#829EBF',None,3)
            self.rect(x+w*.24,y+h*.2,w*.48,h*.2,'#456C9C',None,14)
            self.rect(x+w*.32,y+h*.73,w*.34,10,'#456C9C',None,4)
        elif kind=='headset':
            self.rect(x+w*.28,y+h*.17,w*.43,h*.55,'#456C9C',None,36)
            self.rect(x+w*.35,y+h*.28,w*.29,h*.49,'#EAF0F8',None,25)
            self.rect(x+w*.23,y+h*.44,w*.17,h*.3,'#243F63',None,9)
            self.rect(x+w*.59,y+h*.44,w*.17,h*.3,'#243F63',None,9)
        else:
            self.rect(x+w*.2,y+h*.2,w*.6,h*.45,'#456C9C',None,6)
            self.rect(x+w*.24,y+h*.24,w*.52,h*.35,'#B8CEE9',None,2)
            self.rect(x+w*.13,y+h*.66,w*.74,9,'#243F63',None,3)

def make_ui():
    pages=[]
    def add(*a,**k):
        c=Canvas(*a,**k); pages.append(c); return c
    c=add('01_注册与登录','欢迎回到校园闲置','M1 账号与权限 / 共用登录入口；注册仅创建普通账号')
    c.card(238,186,492,512);c.text(268,215,'登录',23,INK,True)
    c.field(268,266,'用户名','lin_24',426)
    c.field(268,365,'密码','••••••••••••',426)
    c.button(268,466,'登录',426)
    c.banner(268,530,426,['用户名或密码错误。','统一错误提示不泄露账号是否存在。'],'error')
    c.text(268,627,'角色由服务器确定，不提供角色切换选项。',13,MUTED)
    c.card(752,186,572,512);c.text(784,215,'创建普通账号',23,INK,True)
    c.field(784,266,'用户名 *','3～20位英文、数字或下划线',508)
    c.field(784,365,'密码 *','8～64个字符',508)
    c.field(784,464,'昵称（选填）','不收集学号、手机号或真实姓名',508)
    c.button(784,568,'注册普通账号',508)
    c.text(784,634,'用户名忽略大小写判重；不提供公开管理员注册。',13,MUTED)

    c=add('05_我的商品','我的商品','M2 商品管理 / 只管理本人商品；有历史记录的商品不可物理删除',selected='我的商品')
    c.card(238,186,1086,514);c.tabs(261,207,['全部','草稿 / 待审核','在售 / 已预约','其他状态'],gap=232)
    c.text(261,262,'筛选：全部8种状态 ▾     关键词：不限                         分类：全部 ▾',14,MUTED)
    c.table(260,308,1042,['商品 / 编号','状态','更新时间','可用操作'],[
        ['软件工程教材 / P1042','待审核','11-06 10:20','查看批次 · 撤回'],
        ['护眼台灯 / P1039','在售','11-05 18:30','编辑重审 · 下架'],
        ['无线耳机 / P1035','已预约','11-05 14:00','查看预约（禁编辑）'],
        ['旧笔记 / P1030','草稿（从未提交）','11-04 20:16','编辑 · 提交 · 删除'],
        ['电子词典 / P1028','审核驳回','11-03 09:35','查看原因 · 修改重提']], [340,220,190,292],rowh=57)
    c.text(260,659,'其他状态：已下架、违规下架、已成交；终态商品仅查看历史。',13,MUTED)
    c.button(1160,111,'发布商品',164)

    c=add('10_商品审核','审核工作台','M3 审核与违规治理 / 仅展示非草稿；当前审核批次 RV3042',True,'审核工作台')
    c.card(238,186,450,517);c.text(263,209,'待审核商品',19,INK,True)
    c.field(263,253,'关键词 / 分类','全部待审核商品',400)
    c.table(260,355,407,['商品','提交批次'],[['软件工程教材','RV3042'],['护眼台灯','RV3040'],['折叠书架','RV3038']],[245,162],rowh=64)
    c.card(710,186,614,517);c.tag(735,209,'待审核');c.text(735,253,'软件工程教材',23,INK,True)
    c.lines(735,300,['卖家 chen_26 · 教材书籍 / 九成新 · ¥38.00','描述：无缺页，少量铅笔标注。','批次 RV3042 · 内容版本 3 · 页面状态版本 8'],14,step=31)
    c.field(735,411,'驳回原因（驳回时必填）','请补充图片中无法辨认的书名。',564)
    c.button(735,523,'审核通过',170);c.button(925,523,'填写原因驳回',220,False)
    c.banner(735,591,564,['旧批次、已撤回或内容版本已变化时，审核请求被拒绝。','管理员不能直接修改商品内容。'])

    c=add('02_商品集市','发现下一件好物','M4 商品查询 / 仅展示在售商品；游客也可以浏览')
    c.card(238,186,1086,144)
    c.field(260,204,'关键词','搜索标题和描述',320)
    c.field(600,204,'分类','全部分类  ▾',184)
    c.field(804,204,'最低价 / 最高价','¥ 0.01  至  ¥ 99999.99',278)
    c.button(1100,231,'查询',196)
    c.text(260,301,'分类：教材书籍 / 数码电子 / 生活用品 / 文体用品 / 其他（设计选项）',12,MUTED)
    c.text(238,350,'共 4 件在售商品',16,INK,True);c.text(1000,350,'最近审核发布  ▾',14,MUTED)
    for i,(t,p,k,cat) in enumerate([('软件工程教材','38.00','book','教材书籍 · 九成新'),('护眼学习台灯','65.00','lamp','生活用品 · 九成新'),('无线头戴耳机','120.00','headset','数码电子 · 八成新'),('轻薄笔记本电脑','1880.00','laptop','数码电子 · 八成新')]):
        x=238+i*276;c.card(x,387,258,287);c.art(x+14,401,230,155,k)
        c.text(x+16,571,t,16,INK,True);c.text(x+16,602,cat,12,MUTED)
        c.text(x+16,635,'¥ '+p,22,PRIMARY,True);c.text(x+164,641,'查看详情',13,PRIMARY)
    c.text(238,699,'每页 20 条 · 条件按“且”组合 · 同值按商品编号稳定排序',12,MUTED)
    c.button(1153,689,'1 / 1 页',171,False)

    c=add('07_卖家预约工作台','处理买家预约','M5 预约与成交 / 仅查看本人商品的预约；无自动处理时限',selected='卖家工作台')
    c.card(238,186,1086,262);c.tabs(260,206,['待确认','已确认','历史预约'],gap=180)
    c.table(260,259,1042,['商品 / 预约','买家','状态','操作'],[
        ['护眼台灯 / R2012','wu_25','待确认','确认预约 · 拒绝'],
        ['数码相机 / R2010','gao_24','已确认','标记完成 · 取消']], [420,180,180,262],rowh=58)
    c.card(238,470,1086,232);c.text(263,491,'待确认预约 · 拒绝时填写原因',18,INK,True)
    c.field(263,532,'拒绝原因 *','已与买家沟通，面交时间无法协调。',700)
    c.button(994,559,'拒绝预约',303,True,True)
    c.lines(263,633,['拒绝原因只要求非空；不套用取消原因的1～200字限制。','待确认阶段卖家可确认或拒绝，不能用“取消”代替拒绝。'],13,MUTED,27)

    c=add('12_成交统计','成交统计','M6 成交统计 / 卖家仅看本人；管理员同版式查看全平台',selected='成交统计')
    c.card(238,186,1086,116);c.field(263,203,'完成日期（含边界）','2026-11-01 至 2026-11-06',475)
    c.field(760,203,'商品分类','全部分类  ▾',280);c.button(1062,230,'查询统计',236)
    c.card(238,324,530,130);c.text(264,348,'已标记完成的交易数量',15,MUTED);c.text(264,382,'3 笔',35,PRIMARY,True)
    c.card(790,324,534,130);c.text(816,348,'已完成交易标价合计',15,MUTED);c.text(816,382,'¥ 838.00',35,PRIMARY,True)
    c.card(238,477,1086,225)
    c.table(260,494,1042,['完成日期','商品快照 / 分类','预约时标价'],[['11-02 15:20','教材 · 教材书籍','¥38.00'],['11-04 13:40','耳机 · 数码电子','¥120.00'],['11-06 10:50','相机 · 数码电子','¥680.00']],[240,570,232],rowh=38)
    c.text(260,666,'按预约时标价计算，未核验实际付款；取消、拒绝及违规终止均不计入。',13,MUTED)

    c=add('13_管理员审计日志','审计日志','M7 历史与审计 / 只读查询；不提供修改、删除或导出',True,'审计日志')
    c.card(238,186,1086,163);c.field(262,205,'时间区间','11-01 至 11-06',254)
    c.field(534,205,'操作者 / 对象','lin_24 / P1035',254);c.field(806,205,'类型 / 结果','全部 / 全部  ▾',254)
    c.button(1080,232,'查询日志',219)
    c.text(262,317,'只展示授权元数据；密码、密码哈希、完整私人留言均不进入日志。',13,MUTED)
    c.card(238,371,1086,331)
    c.table(260,393,1042,['时间 / 操作者','对象 / 操作','前后状态','结果'],[
        ['10:31:00 / lin_24 (USER)','R2007 / 创建预约','在售 → 已预约','成功'],
        ['10:32:00 / admin (ADMIN)','P1035 / 违规下架','已预约 → 违规下架','成功'],
        ['10:32:01 / wu_25 (USER)','P1035 / 旧预约请求','无变化','拒绝：状态过期'],
        ['10:35:00 / admin (ADMIN)','R2015 / 留言访问','记录原因及访问时间','成功留痕']], [300,275,267,200],rowh=51)
    c.text(260,663,'普通用户仅在业务详情看本人相关历史，不进入此管理日志页面。',13,MUTED)

    for index, page in enumerate(pages, 1):
        page.name = f'界面{index}'
    return pages

def save_pages(pages):
    mxfile=ET.Element('mxfile',host='app.diagrams.net',type='device',version='32.6.10')
    manifest=[]
    for index, c in enumerate(pages, 1):
        diagram=ET.SubElement(mxfile,'diagram',id=f'ui-{index:02d}',name=c.name)
        model=ET.SubElement(diagram,'mxGraphModel',dx='1366',dy='768',grid='1',gridSize='8',guides='1',tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth='1366',pageHeight='768',math='0',shadow='0')
        root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
        svg=ET.Element('svg',xmlns='http://www.w3.org/2000/svg',width='1366',height='768',viewBox='0 0 1366 768')
        for i,e in enumerate(c.e,2):
            if e['kind']=='rect':
                style=f"rounded={1 if e['radius'] else 0};absoluteArcSize=1;arcSize=10;whiteSpace=wrap;html=0;fillColor={e['fill']};strokeColor={e['stroke'] or 'none'};"
                value='';w,h=e['w'],e['h'];y=e['y']
                ET.SubElement(svg,'rect',x=str(e['x']),y=str(y),width=str(w),height=str(h),rx=str(e['radius']),fill=e['fill'],stroke=e['stroke'] or 'none')
            else:
                # Explicit fixed height and generous width prevent text clipping in diagrams.net export.
                w=max(20, sum(e['size']*(1 if ord(ch)>255 else .58) for ch in e['text'])+12)
                h=e['size']+12;y=e['y']-2
                style=f"text;html=0;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=nowrap;overflow=visible;fontFamily=Microsoft YaHei;fontSize={e['size']};fontColor={e['color']};fontStyle={1 if e['bold'] else 0};spacing=0;"
                value=e['text']
                t=ET.SubElement(svg,'text',x=str(e['x']),y=str(e['y']+e['size']),fill=e['color'],attrib={'font-family':'Microsoft YaHei, sans-serif','font-size':str(e['size']),'font-weight':'700' if e['bold'] else '400'})
                t.text=value
            cell=ET.SubElement(root,'mxCell',id=str(i),value=value,style=style,vertex='1',parent='1')
            ET.SubElement(cell,'mxGeometry',x=str(e['x']),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        ET.ElementTree(svg).write(UI_SOURCE/f'{c.name}.svg',encoding='utf-8',xml_declaration=True)
        manifest.append({'name':c.name,'title':c.title,'subtitle':c.subtitle,'elements':len(c.e)})
    ET.ElementTree(mxfile).write(UI_SOURCE/'校园二手交易系统.drawio',encoding='utf-8',xml_declaration=True)
    (UI_SOURCE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate only the seven final editable UI pages.')
    parser.add_argument('--output', type=Path, default=UI_SOURCE,
                        help='UI source output directory (default: src/ui). PNGs are exported separately.')
    args = parser.parse_args()
    UI_SOURCE = args.output.resolve()
    UI_SOURCE.mkdir(parents=True, exist_ok=True)
    save_pages(make_ui())
    print(f'Generated 7 editable UI pages in {UI_SOURCE}')
