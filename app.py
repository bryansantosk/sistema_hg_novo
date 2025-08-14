# app.py — HG Moto Peças (Flask 3.x compat / Render Postgres / init DB no import)
import os
import json
from functools import wraps
from datetime import date
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy

# -----------------------------
# App & DB config
# -----------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_PATH, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_PATH)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_super_secreta')

# Render Postgres via DATABASE_URL, fallback SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(INSTANCE_PATH, 'banco.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def hoje_iso():
    return date.today().strftime('%Y-%m-%d')

# -----------------------------
# Models
# -----------------------------
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), unique=True, nullable=False)
    senha = db.Column(db.String(120), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)   # código
    nome = db.Column(db.String(200), nullable=False)
    custo = db.Column(db.Float, default=0.0)
    preco_varejo = db.Column(db.Float, default=0.0)
    preco_atacado = db.Column(db.Float, default=0.0)
    estoque = db.Column(db.Integer, default=0)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    categoria = db.relationship('Categoria')

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20), nullable=False)  # YYYY-MM-DD
    tipo = db.Column(db.String(20), nullable=False)  # 'venda' | 'entrada' | 'saida'
    valor = db.Column(db.Float, default=0.0)
    forma_pagamento = db.Column(db.String(50))       # só em 'venda'
    observacoes = db.Column(db.Text)
    itens = db.Column(db.Text)  # JSON [{id, nome, qtd, preco}, ...] só em 'venda'

class Caixa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20), unique=True)     # YYYY-MM-DD
    saldo_inicial = db.Column(db.Float, default=0.0)
    aberto = db.Column(db.Boolean, default=True)

class Lancamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20))
    tipo = db.Column(db.String(10))  # 'entrada' | 'saida'
    descricao = db.Column(db.String(200))
    valor = db.Column(db.Float, default=0.0)

class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_criacao = db.Column(db.String(20), default=lambda: hoje_iso())
    cliente_nome = db.Column(db.String(200))
    cliente_telefone = db.Column(db.String(50))
    moto_modelo = db.Column(db.String(120))
    moto_ano = db.Column(db.String(20))
    status = db.Column(db.String(20), default='aberto')  # 'aberto' | 'fechado'
    itens = db.Column(db.Text)  # JSON: [{id, nome, qtd, preco}, ...]
    total = db.Column(db.Float, default=0.0)
    forma_pagamento = db.Column(db.String(50))  # preenchido ao fechar

# -----------------------------
# Inicialização de DB (compatível Flask 3.x)
# -----------------------------
# Cria o schema e o usuário padrão assim que o módulo é importado (funciona no Render e local)
with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(nome='HGMOTO').first():
        db.session.add(Usuario(nome='HGMOTO', senha='hgmotopecas2025'))
        db.session.commit()

# Fecha automaticamente qualquer caixa de dia anterior (pós 00:00)
@app.before_request
def fechar_caixas_antigos():
    hoje = hoje_iso()
    try:
        abertos_antigos = Caixa.query.filter(Caixa.aberto == True, Caixa.data != hoje).all()
        if abertos_antigos:
            for c in abertos_antigos:
                c.aberto = False
            db.session.commit()
    except Exception:
        # Se DB estiver indisponível por algum motivo no primeiro request, apenas ignora (DB já foi criado no import)
        pass

# -----------------------------
# Auth helper
# -----------------------------
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

# -----------------------------
# Auth / Home
# -----------------------------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        senha = request.form.get('senha','').strip()
        u = Usuario.query.filter_by(nome=nome, senha=senha).first()
        if u:
            session['usuario_id'] = u.id
            return redirect(url_for('index'))
        flash('Credenciais inválidas', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# -----------------------------
# Categorias
# -----------------------------
@app.route('/categorias', methods=['GET','POST'])
@login_required
def categorias():
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        if nome:
            if not Categoria.query.filter_by(nome=nome).first():
                db.session.add(Categoria(nome=nome))
                db.session.commit()
            else:
                flash('Categoria já existe.', 'warning')
        return redirect(url_for('categorias'))
    cats = Categoria.query.order_by(Categoria.nome).all()
    return render_template('categorias.html', categorias=cats)

@app.route('/categorias/<int:id>/excluir', methods=['POST'])
@login_required
def categoria_excluir(id):
    cat = Categoria.query.get_or_404(id)
    # desvincula categoria dos produtos e apaga
    for p in Produto.query.filter_by(categoria_id=cat.id).all():
        p.categoria_id = None
    db.session.delete(cat)
    db.session.commit()
    flash('Categoria excluída.', 'success')
    return redirect(url_for('categorias'))

# -----------------------------
# Produtos
# -----------------------------
@app.route('/produtos')
@login_required
def produtos():
    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template('produtos.html', categorias=categorias)

@app.route('/produtos/ver_todos')
@login_required
def produtos_ver_todos():
    q = request.args.get('q','').strip().lower()
    query = Produto.query
    if q:
        if q.isdigit():
            query = query.filter((Produto.id==int(q)) | (Produto.nome.ilike(f'%{q}%')))
        else:
            query = query.filter(Produto.nome.ilike(f'%{q}%'))
    itens = query.order_by(Produto.id.asc()).all()
    return render_template('produtos_todos.html', produtos=itens, q=q)

@app.route('/produtos/novo', methods=['GET','POST'])
@login_required
def novo_produto():
    categorias = Categoria.query.order_by(Categoria.nome).all()
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        custo = float(request.form.get('custo', 0) or 0)
        varejo = float(request.form.get('preco_varejo', 0) or 0)
        atacado = float(request.form.get('preco_atacado', 0) or 0)
        estoque = int(request.form.get('estoque', 0) or 0)
        cat_id = request.form.get('categoria_id') or None
        if nome:
            p = Produto(
                nome=nome, custo=custo, preco_varejo=varejo,
                preco_atacado=atacado, estoque=estoque,
                categoria_id=int(cat_id) if cat_id else None
            )
            db.session.add(p)
            db.session.commit()
            flash(f'Produto criado. Código #{p.id:03d}', 'success')
            return redirect(url_for('produtos_ver_todos'))
    return render_template('novo_produto.html', categorias=categorias)

@app.route('/produtos/<int:id>/excluir', methods=['POST'])
@login_required
def produto_excluir(id):
    p = Produto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    flash('Produto excluído.', 'success')
    return redirect(url_for('produtos_ver_todos'))

# -----------------------------
# Movimentações (Vendas / Entradas / Saídas)
# -----------------------------
@app.route('/movimentacoes', methods=['GET','POST'])
@login_required
def movimentacoes():
    tipo = request.args.get('tipo','venda')  # aba ativa

    if request.method == 'POST':
        tipo_form = request.form.get('tipo','venda')
        valor = float(request.form.get('valor',0) or 0)
        forma = request.form.get('forma_pagamento','')
        obs = request.form.get('observacoes','')
        itens_json = request.form.get('itens','')  # vendas: json de itens

        mov = Movimentacao(
            data=hoje_iso(),
            tipo=tipo_form,
            valor=valor,
            forma_pagamento=forma if tipo_form == 'venda' else None,
            observacoes=obs,
            itens=itens_json if tipo_form == 'venda' else None
        )
        db.session.add(mov)

        # impacto no caixa via lançamentos
        if tipo_form == 'venda':
            db.session.add(Lancamento(data=hoje_iso(), tipo='entrada', descricao='Venda', valor=valor))
            # baixa de estoque se itens informados
            try:
                items = json.loads(itens_json) if itens_json else []
                for it in items:
                    pid = int(it.get('id',0))
                    qtd = int(it.get('qtd',1))
                    prod = Produto.query.get(pid)
                    if prod:
                        prod.estoque = max(0, (prod.estoque or 0) - qtd)
            except Exception:
                pass
        elif tipo_form == 'entrada':
            db.session.add(Lancamento(data=hoje_iso(), tipo='entrada', descricao='Entrada manual', valor=valor))
        elif tipo_form == 'saida':
            db.session.add(Lancamento(data=hoje_iso(), tipo='saida', descricao='Saída manual', valor=valor))

        db.session.commit()
        flash('Movimentação registrada.', 'success')
        return redirect(url_for('movimentacoes', tipo=tipo_form))

    # GET — carrega produtos e movimentos do dia com proteção contra DB frio
    try:
        produtos = Produto.query.order_by(Produto.nome).all()
        do_dia = Movimentacao.query.filter_by(data=hoje_iso()).all()
        vendas = [m for m in do_dia if m.tipo=='venda']
        entradas = [m for m in do_dia if m.tipo=='entrada']
        saidas = [m for m in do_dia if m.tipo=='saida']
    except Exception as e:
        app.logger.error(f"Erro carregando Movimentações: {e}")
        flash('Erro ao carregar movimentações. O banco pode estar inicializando, tente recarregar.', 'danger')
        produtos, vendas, entradas, saidas = [], [], [], []

    return render_template('movimentacoes.html',
                           produtos=produtos, tipo=tipo,
                           vendas=vendas, entradas=entradas, saidas=saidas)

# -----------------------------
# Caixa
# -----------------------------
@app.route('/caixa')
@login_required
def caixa():
    hoje = hoje_iso()
    c = Caixa.query.filter_by(data=hoje).first()
    lancs = Lancamento.query.filter_by(data=hoje).all()
    total_entradas = sum(l.valor for l in lancs if l.tipo=='entrada')
    total_saidas = sum(l.valor for l in lancs if l.tipo=='saida')
    saldo_inicial = c.saldo_inicial if c else 0.0
    saldo_atual = saldo_inicial + total_entradas - total_saidas
    return render_template('caixa.html', caixa=c, total_entradas=total_entradas,
                           total_saidas=total_saidas, saldo_atual=saldo_atual)

@app.route('/abrir_caixa', methods=['POST'])
@login_required
def abrir_caixa():
    valor = float(request.form.get('valor',0) or 0)
    hoje = hoje_iso()
    c = Caixa.query.filter_by(data=hoje).first()
    if c:
        c.saldo_inicial = valor
        c.aberto = True
    else:
        db.session.add(Caixa(data=hoje, saldo_inicial=valor, aberto=True))
    db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/fechar_caixa', methods=['POST'])
@login_required
def fechar_caixa():
    hoje = hoje_iso()
    c = Caixa.query.filter_by(data=hoje).first()
    if c:
        c.aberto = False
        db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/reabrir_caixa', methods=['POST'])
@login_required
def reabrir_caixa():
    hoje = hoje_iso()
    c = Caixa.query.filter_by(data=hoje).first()
    if not c:
        flash('Ainda não existe caixa para hoje. Abra o caixa primeiro.', 'warning')
        return redirect(url_for('caixa'))
    if c.data != hoje:
        flash('Caixa anterior não pode ser reaberto. Consulte em Fechamentos.', 'danger')
        return redirect(url_for('caixa'))
    if c.aberto:
        flash('O caixa de hoje já está ABERTO.', 'info')
    else:
        c.aberto = True
        db.session.commit()
        flash('Caixa de hoje reaberto.', 'success')
    return redirect(url_for('caixa'))

@app.route('/caixas_anteriores')
@login_required
def caixas_anteriores():
    caixas = Caixa.query.order_by(Caixa.data.desc()).all()
    resumo = []
    for c in caixas:
        lancs = Lancamento.query.filter_by(data=c.data).all()
        entradas = sum(l.valor for l in lancs if l.tipo=='entrada')
        saidas = sum(l.valor for l in lancs if l.tipo=='saida')
        saldo_final = c.saldo_inicial + entradas - saidas
        resumo.append({
            'data': c.data,
            'inicial': c.saldo_inicial,
            'entradas': entradas,
            'saidas': saidas,
            'final': saldo_final,
            'aberto': c.aberto
        })
    return render_template('caixas_anteriores.html', caixas=resumo)

# -----------------------------
# Orçamentos
# -----------------------------
@app.route('/orcamentos')
@login_required
def orcamentos():
    lista = Orcamento.query.order_by(Orcamento.id.desc()).all()
    return render_template('orcamentos.html', orcamentos=lista)

@app.route('/orcamentos/novo', methods=['GET','POST'])
@login_required
def orcamento_novo():
    if request.method == 'POST':
        cliente_nome = request.form.get('cliente_nome','').strip()
        cliente_telefone = request.form.get('cliente_telefone','').strip()
        moto_modelo = request.form.get('moto_modelo','').strip()
        moto_ano = request.form.get('moto_ano','').strip()
        o = Orcamento(cliente_nome=cliente_nome, cliente_telefone=cliente_telefone,
                      moto_modelo=moto_modelo, moto_ano=moto_ano, itens=json.dumps([]),
                      total=0.0, status='aberto')
        db.session.add(o)
        db.session.commit()
        return redirect(url_for('orcamento_detalhe', id=o.id))
    return render_template('orcamento_novo.html')

@app.route('/orcamentos/<int:id>', methods=['GET','POST'])
@login_required
def orcamento_detalhe(id):
    o = Orcamento.query.get_or_404(id)
    produtos = Produto.query.order_by(Produto.nome).all()

    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'add_item':
            pid = int(request.form.get('produto_id'))
            qtd = int(request.form.get('qtd',1))
            prod = Produto.query.get(pid)
            itens = json.loads(o.itens) if o.itens else []
            itens.append({'id': prod.id, 'nome': prod.nome, 'qtd': qtd, 'preco': prod.preco_varejo})
            o.itens = json.dumps(itens)
            o.total = sum(it['qtd']*it['preco'] for it in itens)
            db.session.commit()
            return redirect(url_for('orcamento_detalhe', id=id))

        if acao == 'rm_item':
            idx = int(request.form.get('idx'))
            itens = json.loads(o.itens) if o.itens else []
            if 0 <= idx < len(itens):
                itens.pop(idx)
            o.itens = json.dumps(itens)
            o.total = sum(it['qtd']*it['preco'] for it in itens)
            db.session.commit()
            return redirect(url_for('orcamento_detalhe', id=id))

    itens = json.loads(o.itens) if o.itens else []
    return render_template('orcamento_detalhe.html', o=o, itens=itens, produtos=produtos)

@app.route('/orcamentos/<int:id>/fechar', methods=['POST'])
@login_required
def orcamento_fechar(id):
    o = Orcamento.query.get_or_404(id)
    if o.status != 'fechado':
        forma = request.form.get('forma_pagamento','')
        o.status = 'fechado'
        o.forma_pagamento = forma
        db.session.add(Movimentacao(
            data=hoje_iso(), tipo='venda', valor=o.total,
            forma_pagamento=forma, observacoes=f'Orçamento #{o.id} fechado',
            itens=o.itens
        ))
        db.session.add(Lancamento(data=hoje_iso(), tipo='entrada', descricao=f'Orçamento #{o.id}', valor=o.total))
        db.session.commit()
        flash('Orçamento fechado e lançado no caixa.', 'success')
    return redirect(url_for('orcamentos'))

# -----------------------------
# Init (útil quando roda local com python app.py)
# -----------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(nome='HGMOTO').first():
            db.session.add(Usuario(nome='HGMOTO', senha='hgmotopecas2025'))
            db.session.commit()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
