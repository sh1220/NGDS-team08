# NGDS 아키텍처 다이어그램 생성기. 레포 루트에서: python3 docs/generators/architecture.py → draw.io로 PNG 내보내기
import html
cells=[]; n=[0]
def nid(): n[0]+=1; return f"c{n[0]}"
def esc(s): return html.escape(s.replace("\n","<br>"), quote=True)
SI="https://cdn.simpleicons.org/{}/{}"
LBL="verticalLabelPosition=bottom;verticalAlign=top;html=1;fontSize=13;fontColor=#232F3E;whiteSpace=nowrap;labelBackgroundColor=#FFFFFF;"
TOP=LBL.replace("verticalLabelPosition=bottom;verticalAlign=top","verticalLabelPosition=top;verticalAlign=bottom")
S=56
def grp(t,x,y,w,h,stroke,font,dashed=0,align="left"):
    i=nid(); cells.append(f'<mxCell id="{i}" value="{esc(t)}" style="rounded=1;arcSize=2;whiteSpace=wrap;html=1;fillColor=none;strokeColor={stroke};fontColor={font};dashed={dashed};verticalAlign=top;align={align};spacingLeft=12;spacingRight=12;spacingTop=6;fontSize=14;fontStyle=1;strokeWidth=1.5;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'); return i
def logo(t,cx,y,slug,color,top=False):
    i=nid(); cells.append(f'<mxCell id="{i}" value="{esc(t)}" style="shape=image;imageAspect=1;aspect=fixed;strokeColor=none;fillColor=none;image={SI.format(slug,color)};{TOP if top else LBL}" vertex="1" parent="1"><mxGeometry x="{cx-S/2}" y="{y}" width="{S}" height="{S}" as="geometry"/></mxCell>'); return i
def aws(t,cx,y,res,fill,top=False):
    i=nid(); cells.append(f'<mxCell id="{i}" value="{esc(t)}" style="sketch=0;outlineConnect=0;gradientColor=none;strokeColor=#ffffff;fillColor={fill};dashed=0;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{res};{TOP if top else LBL}" vertex="1" parent="1"><mxGeometry x="{cx-S/2}" y="{y}" width="{S}" height="{S}" as="geometry"/></mxCell>'); return i
def users(t,cx,y,top=False):
    i=nid(); cells.append(f'<mxCell id="{i}" value="{esc(t)}" style="sketch=0;outlineConnect=0;fillColor=#232F3E;strokeColor=none;dashed=0;shape=mxgraph.aws4.users;{TOP if top else LBL}" vertex="1" parent="1"><mxGeometry x="{cx-S/2}" y="{y}" width="{S}" height="{S}" as="geometry"/></mxCell>'); return i
def text(t,x,y,w,h,size=13):
    i=nid(); cells.append(f'<mxCell id="{i}" value="{esc(t)}" style="text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize={size};fontColor=#232F3E;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'); return i
def e(s,t,label="",color="#232F3E",dashed=0,ex=None,en=None,pts=(),lx=None,ly=None):
    i=nid(); io=""
    if ex: io+=f"exitX={ex[0]};exitY={ex[1]};exitDx=0;exitDy=0;"
    if en: io+=f"entryX={en[0]};entryY={en[1]};entryDx=0;entryDy=0;"
    p="".join(f'<mxPoint x="{a}" y="{b}"/>' for a,b in pts)
    lp=(f' x="{lx}"' if lx is not None else '')+(f' y="{ly}"' if ly is not None else '')
    arr=f'<Array as="points">{p}</Array>' if pts else ''
    cells.append(f'<mxCell id="{i}" value="{esc(label)}" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=12;fontColor={color};fontStyle=1;strokeColor={color};strokeWidth=2;dashed={dashed};endArrow=block;endFill=1;labelBackgroundColor=#FFFFFF;{io}" edge="1" parent="1" source="{s}" target="{t}"><mxGeometry{lp} relative="1" as="geometry">{arr}</mxGeometry></mxCell>')
R,L,T,B=(1,.5),(0,.5),(.5,0),(.5,1)
BLUE,RED,GH,ORG,GRN,PUR,GRY="#326CE5","#DD344C","#2088FF","#E57000","#1E8E3E","#8C4FFF","#879196"

# ---------- 외부: GitHub ----------
grp("GitHub (인터넷)",320,20,1100,220,GRY,"#5A6C72",dashed=1)
dev=users("팀원\nkubeconfig 그룹 ngds-devs",150,150,top=True)
repo=logo("NGDS-team08 (public)\n앱 코드 · 차트 2개",450,150,"github","181717",top=True)
act=logo("GitHub Actions (호스팅)\nci.yml: lint · build\ndeploy.yml: 이미지 빌드",800,150,"githubactions",GH[1:],top=True)
ghcr=logo("GHCR (public)\nngds-team08-mcp:커밋7자리",1150,150,"docker","2496ED",top=True)
adm=logo("관리자\nEnvironment 승인",1560,150,"apple","000000",top=True)

# ---------- 홈랩 ----------
grp("Home Lab  ·  Proxmox VE 클러스터 (미니 PC 2대)",320,290,1940,960,"#00A4A6","#147EBA",dashed=1,align="right")
grp("Proxmox LXC",350,340,250,460,PUR,PUR)
appr=logo("앱 러너 LXC 112\n라벨 ngds · 디스크엔 ngds-ci만\n수집기 권한은 승인 시 secret",475,640,"githubactions",GH[1:])

grp("Kubernetes  ·  kubeadm, VM 3대 (k8s-cp · k8s-w1 · k8s-w2)",660,340,1580,880,BLUE,BLUE)
gn=grp("ns ngds  ·  Pod Security restricted\n팀원: 배포·exec·부하 파드 / 앱 러너: 배포만",690,380,740,560,BLUE,BLUE)
mcp=logo("MCP 서버 (Deployment)\nFastMCP :8000/mcp\ntool 9개",810,500,"python","3776AB")
pg=logo("PostgreSQL 16\n(StatefulSet, uid 999)\n장애 주입 대상",1060,500,"postgresql","4169E1")
pgx=logo("postgres_exporter\n사이드카 :9187",1310,500,"prometheus","879196")
neo=logo("Neo4j (StatefulSet)\nKG: 증상 → 원인\nemptyDir, make seed",810,780,"neo4j","4581C3")
pvc=aws("PVC 1Gi (postgres 데이터)\nCSI가 VM 디스크로 붙임",1060,780,"elastic_block_store",GRN)
load=logo("부하 파드 (pgbench)\nmake fault-*",1310,780,"gnubash","4EAA25")

gm=grp("ns ngds-monitoring  ·  privileged\n배포: monitoring.yml(관리자 승인) / 팀원: 조회만",1460,380,750,560,RED,RED)
prom=logo("Prometheus\nscrape 15s · 보존 6h\nClusterRole 조회 전용",1590,500,"prometheus","E6522C")
ksm=logo("kube-state-metrics\n재시작 · OOMKilled",1840,500,"kubernetes","326CE5")
nexp=logo("node-exporter (DS)\nhostNetwork :9100\nhostPath /proc /sys /",2090,500,"prometheus","E6522C")
loki=logo("Loki\n로그 저장 · 보존 24h",1590,780,"grafana","F46800")
ptail=logo("promtail (DaemonSet)\nhostPath 읽기 전용",1840,780,"grafana","F46800")

grp("각 노드 (VM)  ·  kube-system · tfstate",690,990,1520,210,GRY,"#5A6C72")
cil=logo("Cilium\nCNI · LoadBalancer",810,1060,"cilium","F8C517")
csi=logo("Proxmox CCM · CSI\nPVC → VM 디스크",1060,1060,"proxmox",ORG[1:])
tfs=aws("tfstate (ns)\nTerraform state",1310,1060,"secrets_manager",RED)
kube=logo("kubelet · cAdvisor\n:10250 컨테이너 지표",1840,1060,"kubernetes","326CE5")
vlog=aws("/var/log/pods\n파드 로그 파일",2090,1060,"logs","#E7157B")

claude=logo("LLM 클라이언트\n(Claude 등)",150,470,"claude","D97757")

# ---------- 배포 흐름 (파랑) ----------
e(dev,repo,"① PR · merge",GH,ex=R,en=L)
e(repo,act,"② 워크플로",GH,ex=R,en=L)
e(act,ghcr,"③ 이미지 push",GH,ex=R,en=L)
e(act,appr,"④ deploy job\n(self-hosted · ngds)",GH,ex=B,en=L,pts=[(800,250),(335,250),(335,668)],lx=-0.42)
e(appr,gn,"⑤ helm\nupgrade",GH,ex=R,en=(0,.5),lx=-0.62)
e(ghcr,gn,"⑥ 이미지 pull",GH,dashed=1,ex=B,en=(.62,0),lx=0.45)
# ---------- 관리자 흐름 (보라) ----------
e(adm,act,"⑦ 승인\n(Environment monitoring)",PUR,ex=B,en=(.8,1),pts=[(1560,212),(822,212)],lx=0.25)
e(appr,gm,"⑧ helm upgrade ngds-monitoring\n(승인 후 Environment secret)",PUR,ex=(1,.85),en=(.2,1),pts=[(630,688),(630,965),(1610,965)],lx=0.1)

# ---------- 데이터 흐름 ----------
e(prom,pgx,"scrape",ORG,ex=L,en=R)
e(prom,ksm,"scrape",ORG,ex=(1,.3),en=(0,.3))
e(prom,nexp,"scrape",ORG,ex=(.7,0),en=T,pts=[(1607,470),(2090,470)],lx=0.2)
e(prom,kube,"scrape (nodes/metrics)",ORG,ex=(1,.85),en=T,pts=[(1715,548),(1715,975),(1840,975)],lx=0.55)
e(ptail,vlog,"tail ngds_*",ORG,ex=R,en=T,pts=[(2090,808)])
e(ptail,loki,"push",ORG,ex=L,en=R,lx=0.55)
e(mcp,prom,"PromQL",GRN,ex=(.3,0),en=(.3,0),pts=[(827-10,440),(1573,440)],lx=0.1)
e(mcp,loki,"LogQL",GRN,ex=(.7,0),en=L,pts=[(827+12-6,455),(1490,455),(1490,808)],lx=-0.2)
e(mcp,neo,"Cypher",GRN,ex=(0,.8),en=(0,.5),pts=[(715,545),(715,808)])
e(claude,mcp,"MCP\n(port-forward)",GRN,ex=R,en=(0,.3),lx=-0.86)
e(load,pg,"부하 · 락 경합",GRY,dashed=1,ex=(0,.3),en=(1,.75),pts=[(1240,797),(1240,542)])

text("""<b>흐름 읽는 법</b><br>
<font color="#2088FF"><b>파랑 ①~⑥ 앱 배포</b></font>: 팀원 PR → 머지 → 호스팅 러너가 이미지 빌드·GHCR push → 홈랩 앱 러너가 <code>charts/ngds</code>를 ns ngds에 helm upgrade<br>
<font color="#8C4FFF"><b>보라 ⑦~⑧ 수집기 배포</b></font>: <code>charts/ngds-monitoring</code> 변경 머지 → monitoring.yml이 관리자 승인 대기 → 승인되면 앱 러너가 Environment secret(main 전용)으로 설치<br>
<font color="#E57000"><b>주황 수집</b></font>: Prometheus가 exporter·kubelet을 긁고, promtail이 노드의 ngds 파드 로그를 Loki로 보낸다<br>
<font color="#1E8E3E"><b>초록 분석</b></font>: LLM → MCP → check_health(Prometheus) → get_diagnosis(Neo4j KG) → query_promql/logql로 근거 확인""",340,1290,1000,140)
text("""<b>왜 네임스페이스가 둘인가</b><br>
수집기는 hostPath·hostNetwork·ClusterRole이 필요하다 → 거기에 파드를 만들 수 있으면 노드 root.<br>
그래서 팀원·앱 러너는 restricted인 <b>ngds</b>에서만 파드를 만들고, privileged인 <b>ngds-monitoring</b>은 관리자 승인을 거친 배포만 들어간다.<br>
팀원의 수집기 접근: Prometheus·Loki Service 프록시 <b>GET</b>만 (port-forward·exec 없음). 앱 러너 디스크에는 privileged 권한을 두지 않는다(브랜치 워크플로로 꺼낼 수 있어서) → 승인된 main job에만 secret으로 전달.""",1360,1290,900,140)

diagram='<diagram name="NGDS 아키텍처" id="ngds"><mxGraphModel dx="2300" dy="1550" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="2300" pageHeight="1460" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'+"".join(cells)+'</root></mxGraphModel></diagram>'
open('docs/architecture.drawio','w').write('<mxfile host="drawio">'+diagram+'</mxfile>')
print(len(cells),"cells")
