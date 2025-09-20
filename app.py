# app.py — HG Moto Peças (com ORÇAMENTOS)
# Mantém layout; adiciona lógica/rotas. Flask 3.x + SQLAlchemy 2.x

import os
import json
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_PATH, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_PATH)
app.secret_key = os.environ.get("SECRET_KEY", "chave_super_secreta")

def normalize_db_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

DATABASE_URL = normalize_db_url(os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_INTERNAL_URL"))
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_PATH, "banco.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Timezone fixo
TZ = ZoneInfo("America/Sao_Paulo")
def hoje_data():
    return datetime.now(TZ).date()
def hoje_str():
    return hoje_data().strftime("%Y-%m-%d")

# ----------------- MODELOS -----------------
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)
    senha = db.Column(db.String(120), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(6), unique=True)  # 001, 002...
    nome = db.Column(db.String(120), nullable=False)
    custo = db.Column(db.Float, nullable=False, default=0.0)
    preco_varejo = db.Column(db.Float, nullable=False, default=0.0)
    preco_atacado = db.Column(db.Float, nullable=False, default=0.0)
    estoque = db.Column(db.Integer, default=0)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria.id"), nullable=True)  # opcional
    categoria = db.relationship("Categoria")

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    forma_pagamento = db.Column(db.String(50))
    observacoes = db.Column(db.Text)
    total = db.Column(db.Float, nullable=False, default=0.0)
    itens = db.Column(db.Text)  # JSON

class Caixa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10), unique=True)  # YYYY-MM-DD
    saldo_inicial = db.Column(db.Float, default=0.0)
    aberto = db.Column(db.Boolean, default=False)

class Lancamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    tipo = db.Column(db.String(10))  # 'entrada' ou 'saida'
    descricao = db.Column(db.String(200))
    valor = db.Column(db.Float, default=0.0)

# >>> NOVO: ORÇAMENTO <<<
class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(10), default="aberto")  # 'aberto' | 'fechado'
    data = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    cliente = db.Column(db.String(120), default="")
    moto = db.Column(db.String(120), default="")
    servico = db.Column(db.String(120), default="")
    garantia = db.Column(db.String(50), default="90 DIAS GARANTIA")
    forma_pagamento = db.Column(db.String(50))
    itens = db.Column(db.Text, default="[]")  # JSON: [{codigo, nome, qtd, valor_unit, subtotal}]
    total = db.Column(db.Float, default=0.0)

# --------------- MIGRAÇÃO LEVE ---------------
def ensure_schema():
    db.create_all()
    insp = inspect(db.engine)

    # coluna codigo em produto
    if insp.has_table("produto"):
        cols = [c["name"] for c in insp.get_columns("produto")]
        if "codigo" not in cols:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE produto ADD COLUMN codigo VARCHAR(6);'))
            except Exception:
                pass

    # preencher códigos faltantes
    if insp.has_table("produto"):
        produtos_sem_codigo = Produto.query.filter((Produto.codigo.is_(None)) | (Produto.codigo == "")).all()
        if produtos_sem_codigo:
            existentes = [int(p.codigo) for p in Produto.query.filter(Produto.codigo.is_not(None)).all() if (p.codigo or "").isdigit()]
            sequencia = max(existentes) if existentes else 0
            for p in produtos_sem_codigo:
                sequencia += 1
                p.codigo = f"{sequencia:03d}"
            db.session.commit()

# --------------- LOGIN ---------------
def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        senha = request.form.get("senha","").strip()
        user = Usuario.query.filter_by(nome=nome, senha=senha).first()
        if user:
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("Credenciais inválidas", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --------------- VIRADA 00:00 ---------------
@app.before_request
def virada_automatica():
    try:
        hoje = hoje_str()
        ontem = (hoje_data() - timedelta(days=1)).strftime("%Y-%m-%d")
        cx_ontem = Caixa.query.filter_by(data=ontem, aberto=True).first()
        if cx_ontem:
            cx_ontem.aberto = False
            db.session.commit()
        if not Caixa.query.filter_by(data=hoje).first():
            db.session.add(Caixa(data=hoje, saldo_inicial=0.0, aberto=False))
            db.session.commit()
    except Exception:
        db.session.rollback()

# --------------- ROTAS ----------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")

# -------- PRODUTOS --------
@app.route("/produtos")
@login_required
def produtos():
    q = (request.args.get("q") or "").strip()
    ver = request.args.get("ver") == "1"  # só lista quando ver=1 ou quando há busca
    produtos = []
    if q:
        produtos = Produto.query.filter(
            db.or_(Produto.nome.ilike(f"%{q}%"), Produto.codigo.ilike(f"%{q}%"))
        ).order_by(Produto.id.desc()).all()
        ver = True
    elif ver:
        produtos = Produto.query.order_by(Produto.id.desc()).all()
    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template("produtos.html", produtos=produtos, categorias=categorias, q=q, ver=ver)

@app.route("/produtos/ver_todos")
@login_required
def produtos_ver_todos():
    return redirect(url_for("produtos", ver=1))

@app.route("/produtos/novo", methods=["GET","POST"])
@login_required
def novo_produto():
    categorias = Categoria.query.order_by(Categoria.nome).all()
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        custo = float(request.form.get("custo") or 0)
        varejo = float(request.form.get("varejo") or 0)
        atacado = float(request.form.get("atacado") or 0)
        estoque = int(request.form.get("estoque") or 0)
        categoria_id = request.form.get("categoria") or ""
        categoria_id = int(categoria_id) if str(categoria_id).isdigit() else None
        if not nome:
            flash("Informe o nome do produto", "warning")
            return render_template("novo_produto.html", categorias=categorias)
        existentes = [int(p.codigo) for p in Produto.query.filter(Produto.codigo.is_not(None)).all() if (p.codigo or "").isdigit()]
        proximo = (max(existentes) + 1) if existentes else 1
        codigo = f"{proximo:03d}"
        p = Produto(
            codigo=codigo, nome=nome, custo=custo,
            preco_varejo=varejo, preco_atacado=atacado,
            estoque=estoque, categoria_id=categoria_id
        )
        db.session.add(p)
        db.session.commit()
        flash(f"Produto cadastrado (código {codigo})", "success")
        return redirect(url_for("produtos", ver=1))
    return render_template("novo_produto.html", categorias=categorias)

# Mantém /categorias exatamente
@app.route("/categorias", methods=["GET","POST"])
@login_required
def categorias():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if nome:
            db.session.add(Categoria(nome=nome))
            db.session.commit()
            flash("Categoria criada", "success")
            return redirect(url_for("categorias"))
    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template("categorias.html", categorias=categorias)

@app.route("/categorias/excluir/<int:id>", methods=["POST"])
@login_required
def excluir_categoria(id):
    c = Categoria.query.get_or_404(id)
    vinc = Produto.query.filter_by(categoria_id=c.id).first()
    if vinc:
        flash("Existe produto nessa categoria. Remova/edite o produto antes.", "warning")
        return redirect(url_for("categorias"))
    db.session.delete(c)
    db.session.commit()
    flash("Categoria excluída", "success")
    return redirect(url_for("categorias"))

# -------- API de produtos (para buscas) --------
@app.route("/api/produtos")
@login_required
def api_produtos():
    q = (request.args.get("q") or "").strip()
    query = Produto.query
    if q:
        query = query.filter(
            db.or_(Produto.nome.ilike(f"%{q}%"), Produto.codigo.ilike(f"%{q}%"))
        )
    prods = query.order_by(Produto.nome.asc()).limit(50).all()
    data = [{
        "id": p.id,
        "codigo": p.codigo or "",
        "nome": p.nome,
        "preco_varejo": float(p.preco_varejo or 0),
        "preco_atacado": float(p.preco_atacado or 0),
        "estoque": int(p.estoque or 0)
    } for p in prods]
    return jsonify(data)

# -------- VENDAS (mantido) --------
@app.route("/vendas", methods=["GET","POST"])
@login_required
def vendas():
    q = (request.args.get("q") or "").strip()
    if q:
        produtos = Produto.query.filter(
            db.or_(Produto.nome.ilike(f"%{q}%"), Produto.codigo.ilike(f"%{q}%"))
        ).order_by(Produto.nome.asc()).all()
    else:
        produtos = Produto.query.order_by(Produto.nome.asc()).limit(20).all()

    if request.method == "POST":
        itens_json = request.form.get("itens_json", "").strip()
        itens_list = []
        total = 0.0
        if itens_json:
            try:
                parsed = json.loads(itens_json)
            except Exception:
                parsed = []
            for it in parsed:
                codigo = it.get("codigo","")
                nome = it.get("nome","")
                qtd = int(it.get("qtd", 1))
                preco_unit = float(it.get("preco_unit", 0))
                tipo_preco = it.get("tipo_preco","varejo")
                subtotal = preco_unit * qtd
                total += subtotal
                itens_list.append({
                    "codigo": codigo, "nome": nome, "qtd": qtd,
                    "preco_unit": preco_unit, "tipo_preco": tipo_preco,
                    "subtotal": subtotal
                })
        else:
            itens_str = request.form.get("itens","")
            for pedaco in [p.strip() for p in itens_str.split(",") if p.strip()]:
                try:
                    nome_part, valor_part = pedaco.rsplit(" - R$ ", 1)
                    nome = nome_part.split(" x")[0].strip()
                    qtd = int(nome_part.split(" x")[1])
                    preco_total = float(valor_part.replace(",", "."))
                except Exception:
                    nome = pedaco; qtd = 1; preco_total = 0.0
                prod = Produto.query.filter_by(nome=nome).first()
                codigo = prod.codigo if prod else ""
                preco_unit = (preco_total / qtd) if qtd else 0.0
                total += preco_total
                itens_list.append({
                    "codigo": codigo, "nome": nome, "qtd": qtd,
                    "preco_unit": preco_unit, "tipo_preco": "livre",
                    "subtotal": preco_total
                })

        forma = request.form.get("forma_pagamento","")
        obs = request.form.get("observacoes","")
        v = Venda(
            data=hoje_str(), forma_pagamento=forma, observacoes=obs,
            total=total, itens=json.dumps(itens_list, ensure_ascii=False)
        )
        db.session.add(v); db.session.commit()
        flash("Venda registrada", "success")
        return redirect(url_for("vendas"))
    return render_template("vendas.html", produtos=produtos, q=q)

# -------- MOVIMENTAÇÕES --------
@app.route("/movimentacoes", methods=["GET","POST"])
@login_required
def movimentacoes():
    d = request.args.get("data") or hoje_str()
    vendas = Venda.query.filter_by(data=d).all()
    entradas = Lancamento.query.filter_by(data=d, tipo="entrada").all()
    saidas = Lancamento.query.filter_by(data=d, tipo="saida").all()
    total_vendas = sum(v.total for v in vendas)
    total_entradas = sum(l.valor for l in entradas)
    total_saidas = sum(l.valor for l in saidas)
    return render_template(
        "movimentacoes.html",
        data=d, vendas=vendas, entradas=entradas, saidas=saidas,
        total_vendas=total_vendas, total_entradas=total_entradas, total_saidas=total_saidas
    )

@app.route("/movimentacoes/nova", methods=["POST"])
@login_required
def nova_movimentacao():
    tipo = request.form.get("tipo")
    descricao = (request.form.get("descricao") or "").strip()
    valor = float(request.form.get("valor") or 0)
    data_ref = request.form.get("data") or hoje_str()
    if tipo not in ("entrada","saida"):
        flash("Tipo inválido", "danger")
        return redirect(url_for("movimentacoes"))
    db.session.add(Lancamento(data=data_ref, tipo=tipo, descricao=descricao, valor=valor))
    db.session.commit()
    flash("Movimentação registrada", "success")
    return redirect(url_for("movimentacoes", data=data_ref))

# -------- CAIXA --------
@app.route("/caixa")
@login_required
def caixa():
    d = hoje_str()
    c = Caixa.query.filter_by(data=d).first()
    vendas = Venda.query.filter_by(data=d).all()
    lancs = Lancamento.query.filter_by(data=d).all()
    total_vendas = sum(v.total for v in vendas)
    total_entradas = sum(l.valor for l in lancs if l.tipo == "entrada")
    total_saidas = sum(l.valor for l in lancs if l.tipo == "saida")
    saldo_atual = (c.saldo_inicial if c else 0.0) + total_vendas + total_entradas - total_saidas
    return render_template(
        "caixa.html",
        caixa=c, total_vendas=total_vendas, total_entradas=total_entradas,
        total_despesas=total_saidas, saldo_atual=saldo_atual, lancamentos=lancs
    )

@app.route("/abrir_caixa", methods=["POST"])
@login_required
def abrir_caixa():
    d = hoje_str()
    valor = float(request.form.get("valor") or 0)
    c = Caixa.query.filter_by(data=d).first()
    if not c:
        c = Caixa(data=d, saldo_inicial=valor, aberto=True)
        db.session.add(c)
    else:
        c.saldo_inicial = valor; c.aberto = True
    db.session.commit(); flash("Caixa aberto", "success")
    return redirect(url_for("caixa"))

@app.route("/fechar_caixa", methods=["POST"])
@login_required
def fechar_caixa():
    d = hoje_str(); c = Caixa.query.filter_by(data=d).first()
    if c:
        c.aberto = False; db.session.commit(); flash("Caixa fechado", "success")
    return redirect(url_for("caixa"))

@app.route("/reabrir_caixa", methods=["POST"])
@login_required
def reabrir_caixa():
    d = hoje_str(); c = Caixa.query.filter_by(data=d).first()
    if c:
        c.aberto = True; db.session.commit(); flash("Caixa reaberto", "success")
    return redirect(url_for("caixa"))

@app.route("/caixas_anteriores")
@login_required
def caixas_anteriores():
    caixas = Caixa.query.order_by(Caixa.data.desc()).all()
    resultado = []
    for c in caixas:
        vendas = Venda.query.filter_by(data=c.data).all()
        total_vendas = sum(v.total for v in vendas)
        lancs = Lancamento.query.filter_by(data=c.data).all()
        total_ent = sum(l.valor for l in lancs if l.tipo == "entrada")
        total_des = sum(l.valor for l in lancs if l.tipo == "saida")
        saldo_final = (c.saldo_inicial or 0.0) + total_vendas + total_ent - total_des
        resultado.append({
            "data": c.data, "inicial": c.saldo_inicial or 0.0,
            "vendas": total_vendas, "entradas": total_ent,
            "despesas": total_des, "final": saldo_final, "aberto": c.aberto
        })
    return render_template("caixas_anteriores.html", caixas=resultado)

# -------- RELATÓRIOS --------
def _range_datas(periodo: str):
    hoje_d = hoje_data()
    if periodo == "semanal":
        ini = hoje_d - timedelta(days=6); fim = hoje_d
    else:
        ini = hoje_d.replace(day=1); fim = hoje_d
    return ini, fim

def _coleta(ini: date, fim: date):
    d = ini; entrou = saiu = vendas_total = 0.0
    while d <= fim:
        ds = d.strftime("%Y-%m-%d")
        vendas_total += sum(v.total for v in Venda.query.filter_by(data=ds).all())
        lancs = Lancamento.query.filter_by(data=ds).all()
        entrou += sum(l.valor for l in lancs if l.tipo == "entrada")
        saiu += sum(l.valor for l in lancs if l.tipo == "saida")
        d += timedelta(days=1)
    lucro = (vendas_total + entrou) - saiu
    return entrou, saiu, vendas_total, lucro

@app.route("/relatorios")
@login_required
def relatorios():
    caixas = Caixa.query.all()
    saldo_inicial = sum(c.saldo_inicial or 0 for c in caixas)
    total_vendas = sum(sum(v.total for v in Venda.query.filter_by(data=c.data)) for c in caixas)
    total_despesas = sum(sum(l.valor for l in Lancamento.query.filter_by(data=c.data) if l.tipo == "saida") for c in caixas)
    saldo_final = saldo_inicial + total_vendas - total_despesas
    meses = sorted(set((c.data or "")[:7] for c in caixas if c.data))
    comparativo = []
    for mes in meses:
        cx_mes = [c for c in caixas if (c.data or "").startswith(mes)]
        vendas_mes = sum(sum(v.total for v in Venda.query.filter_by(data=c.data)) for c in cx_mes)
        desp_mes = sum(sum(l.valor for l in Lancamento.query.filter_by(data=c.data) if l.tipo == "saida") for c in cx_mes)
        comparativo.append({"mes": mes, "vendas": f"{vendas_mes:.2f}", "despesas": f"{desp_mes:.2f}", "lucro": f"{(vendas_mes-desp_mes):.2f}"})
    return render_template(
        "relatorios.html",
        saldo_inicial=f"{saldo_inicial:.2f}", total_vendas=f"{total_vendas:.2f}",
        total_despesas=f"{total_despesas:.2f}", saldo_final=f"{saldo_final:.2f}",
        comparativo=comparativo
    )

@app.route("/relatorios/<periodo>")
@login_required
def relatorio_periodo(periodo):
    if periodo not in ("semanal","mensal"):
        flash("Período inválido", "warning")
        return redirect(url_for("relatorios"))
    ini, fim = _range_datas(periodo)
    entrou, saiu, vendas_total, lucro = _coleta(ini, fim)
    return render_template(
        "relatorio_financeiro.html",
        titulo=("Relatório Semanal" if periodo=="semanal" else "Relatório Mensal"),
        data_inicio=ini.strftime("%d/%m/%Y"), data_fim=fim.strftime("%d/%m/%Y"),
        entrou=f"{entrou:.2f}", saiu=f"{saiu:.2f}",
        vendas=f"{vendas_total:.2f}", lucro=f"{lucro:.2f}"
    )

# ---------------- ORÇAMENTOS ----------------
@app.route("/orcamentos")
@login_required
def orcamentos_list():
    abertos = Orcamento.query.filter_by(status="aberto").order_by(Orcamento.id.desc()).all()
    return render_template("orcamentos_list.html", orcamentos=abertos)

@app.route("/orcamentos/fechados")
@login_required
def orcamentos_fechados():
    fechados = Orcamento.query.filter_by(status="fechado").order_by(Orcamento.id.desc()).all()
    return render_template("orcamentos_list_fechados.html", orcamentos=fechados)

@app.route("/orcamentos/novo")
@login_required
def orcamento_novo():
    o = Orcamento(status="aberto", data=hoje_str(), itens="[]", total=0.0)
    db.session.add(o); db.session.commit()
    return redirect(url_for("orcamento_editar", oid=o.id))

@app.route("/orcamentos/<int:oid>", methods=["GET","POST"])
@login_required
def orcamento_editar(oid):
    o = Orcamento.query.get_or_404(oid)
    if request.method == "POST":
        acao = request.form.get("action","salvar")
        o.cliente = request.form.get("cliente","").strip()
        o.moto = request.form.get("moto","").strip()
        o.servico = request.form.get("servico","").strip()
        o.data = request.form.get("data") or hoje_str()
        o.itens = request.form.get("itens_json","[]")
        o.total = float(request.form.get("total") or 0)

        if acao == "finalizar":
            forma = request.form.get("forma_pagamento","").strip()
            if not forma:
                flash("Informe a forma de pagamento para finalizar.", "warning")
                return redirect(url_for("orcamento_editar", oid=o.id))
            o.forma_pagamento = forma
            o.status = "fechado"
            db.session.commit()
            # Gera uma venda (entra no Caixa automaticamente)
            v = Venda(
                data=o.data, forma_pagamento=forma,
                observacoes=f"Orçamento #{o.id} finalizado",
                total=o.total, itens=o.itens
            )
            db.session.add(v); db.session.commit()
            flash("Orçamento finalizado e registrado no Caixa.", "success")
            return redirect(url_for("orcamentos_list"))
        else:
            db.session.commit()
            flash("Orçamento salvo.", "success")
            return redirect(url_for("orcamento_editar", oid=o.id))

    # GET
    try:
        itens = json.loads(o.itens or "[]")
    except Exception:
        itens = []
    return render_template("orcamento_form.html", o=o, itens=itens)

@app.route("/orcamentos/<int:oid>/imprimir")
@login_required
def orcamento_imprimir(oid):
    o = Orcamento.query.get_or_404(oid)
    try:
        itens = json.loads(o.itens or "[]")
    except Exception:
        itens = []
    return render_template("orcamento_print.html", o=o, itens=itens)

# --------------- BOOT (executa também no Render) ---------------
with app.app_context():
    ensure_schema()
    if not Usuario.query.filter_by(nome="HGMOTO").first():
        db.session.add(Usuario(nome="HGMOTO", senha="hgmotopecas2025"))
        db.session.commit()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
