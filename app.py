import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import date
import json
from io import BytesIO

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_PATH, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_PATH)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_super_secreta')

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(INSTANCE_PATH, 'banco.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    senha = db.Column(db.String(120), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    custo = db.Column(db.Float, nullable=False, default=0.0)
    preco_varejo = db.Column(db.Float, nullable=False, default=0.0)
    preco_atacado = db.Column(db.Float, nullable=False, default=0.0)
    estoque = db.Column(db.Integer, default=0)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'))
    categoria = db.relationship('Categoria')

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20), nullable=False)
    forma_pagamento = db.Column(db.String(50))
    observacoes = db.Column(db.Text)
    total = db.Column(db.Float, nullable=False, default=0.0)
    itens = db.Column(db.Text)

class Caixa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20), unique=True)
    saldo_inicial = db.Column(db.Float, default=0.0)
    aberto = db.Column(db.Boolean, default=True)

class Lancamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(20))
    tipo = db.Column(db.String(10))
    descricao = db.Column(db.String(200))
    valor = db.Column(db.Float)

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '').strip()
        user = Usuario.query.filter_by(nome=nome, senha=senha).first()
        if user:
            session['usuario_id'] = user.id
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

@app.route('/produtos')
@login_required
def produtos():
    categorias = Categoria.query.order_by(Categoria.nome).all()
    return render_template('produtos.html', categorias=categorias)

@app.route('/produtos/lista/<int:categoria_id>')
@login_required
def produtos_por_categoria(categoria_id):
    produtos = Produto.query.filter_by(categoria_id=categoria_id).all()
    return render_template('produtos_lista.html', produtos=produtos)

@app.route('/produtos/novo', methods=['GET', 'POST'])
@login_required
def novo_produto():
    categorias = Categoria.query.order_by(Categoria.nome).all()
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        custo = float(request.form.get('custo', 0) or 0)
        varejo = float(request.form.get('varejo', 0) or 0)
        atacado = float(request.form.get('atacado', 0) or 0)
        estoque = int(request.form.get('estoque', 0) or 0)
        categoria_id = request.form.get('categoria') or None
        p = Produto(nome=nome, custo=custo, preco_varejo=varejo, preco_atacado=atacado,
                    estoque=estoque, categoria_id=categoria_id)
        db.session.add(p)
        db.session.commit()
        return redirect(url_for('produtos'))
    return render_template('novo_produto.html', categorias=categorias)

@app.route('/categorias', methods=['GET', 'POST'])
@login_required
def categorias():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        if nome:
            c = Categoria(nome=nome)
            db.session.add(c)
            db.session.commit()
            flash('Categoria criada', 'success')
            return redirect(url_for('categorias'))
    todas = Categoria.query.order_by(Categoria.nome).all()
    return render_template('categorias.html', categorias=todas)

@app.route('/categorias/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_categoria(id):
    c = Categoria.query.get(id)
    if c:
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for('categorias'))

@app.route('/vendas', methods=['GET', 'POST'])
@login_required
def vendas():
    produtos = Produto.query.order_by(Produto.nome).all()
    hoje = date.today().strftime('%Y-%m-%d')
    if request.method == 'POST':
        forma = request.form.get('forma_pagamento','').strip()
        obs = request.form.get('observacoes','').strip()
        total = float(request.form.get('total',0) or 0)
        itens_json = request.form.get('itens')
        v = Venda(data=hoje, forma_pagamento=forma, observacoes=obs, total=total, itens=itens_json)
        db.session.add(v)
        caixa = Caixa.query.filter_by(data=hoje).first()
        if caixa:
            lanc = Lancamento(data=hoje, tipo='entrada', descricao='Venda', valor=total)
            db.session.add(lanc)
        db.session.commit()
        return redirect(url_for('vendas'))
    return render_template('vendas.html', produtos=produtos)

@app.route('/caixa')
@login_required
def caixa():
    hoje = date.today().strftime('%Y-%m-%d')
    caixa = Caixa.query.filter_by(data=hoje).first()
    vendas = Venda.query.filter_by(data=hoje).all()
    total_vendas = sum(v.total for v in vendas) if vendas else 0.0
    lancamentos = Lancamento.query.filter_by(data=hoje).all()
    total_despesas = sum(l.valor for l in lancamentos if l.tipo == 'saida')
    total_entradas = sum(l.valor for l in lancamentos if l.tipo == 'entrada')
    saldo_atual = caixa.saldo_inicial + total_vendas + total_entradas - total_despesas if caixa else 0.0
    return render_template('caixa.html', caixa=caixa, total_vendas=total_vendas,
                           total_despesas=total_despesas, total_entradas=total_entradas,
                           saldo_atual=saldo_atual, lancamentos=lancamentos)

@app.route('/abrir_caixa', methods=['POST'])
@login_required
def abrir_caixa():
    hoje = date.today().strftime('%Y-%m-%d')
    valor = float(request.form.get('valor',0) or 0)
    c = Caixa.query.filter_by(data=hoje).first()
    if c:
        c.saldo_inicial = valor
        c.aberto = True
    else:
        novo = Caixa(data=hoje, saldo_inicial=valor, aberto=True)
        db.session.add(novo)
    db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/fechar_caixa', methods=['POST'])
@login_required
def fechar_caixa():
    hoje = date.today().strftime('%Y-%m-%d')
    c = Caixa.query.filter_by(data=hoje).first()
    if c:
        c.aberto = False
        db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/reabrir_caixa', methods=['POST'])
@login_required
def reabrir_caixa():
    hoje = date.today().strftime('%Y-%m-%d')
    c = Caixa.query.filter_by(data=hoje).first()
    if c:
        c.aberto = True
        db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/lancamento_manual', methods=['POST'])
@login_required
def lancamento_manual():
    hoje = date.today().strftime('%Y-%m-%d')
    descricao = request.form.get('descricao','').strip()
    valor = float(request.form.get('valor',0) or 0)
    tipo = request.form.get('tipo','entrada')
    lanc = Lancamento(data=hoje, tipo=tipo, descricao=descricao, valor=valor)
    db.session.add(lanc)
    db.session.commit()
    return redirect(url_for('caixa'))

@app.route('/caixas_anteriores')
@login_required
def caixas_anteriores():
    caixas = Caixa.query.order_by(Caixa.data.desc()).all()
    resultado = []
    for c in caixas:
        vendas = Venda.query.filter_by(data=c.data).all()
        total_vendas = sum(v.total for v in vendas)
        lancs = Lancamento.query.filter_by(data=c.data).all()
        total_des = sum(l.valor for l in lancs if l.tipo == 'saida')
        total_ent = sum(l.valor for l in lancs if l.tipo == 'entrada')
        saldo_final = c.saldo_inicial + total_vendas + total_ent - total_des
        resultado.append({'data': c.data, 'inicial': c.saldo_inicial, 'vendas': total_vendas,
                          'entradas': total_ent, 'despesas': total_des, 'final': saldo_final, 'aberto': c.aberto})
    return render_template('caixas_anteriores.html', caixas=resultado)

@app.route('/relatorios')
@login_required
def relatorios():
    caixas = Caixa.query.order_by(Caixa.data).all()
    if not caixas:
        return render_template('relatorios.html', vendas_por_forma={}, top_produtos=[], despesas=[], comparativo=[])
    ultimo = caixas[-1]
    vendas = Venda.query.filter_by(data=ultimo.data).all()
    lancs = Lancamento.query.filter_by(data=ultimo.data).all()
    saldo_inicial = ultimo.saldo_inicial
    total_vendas = sum(v.total for v in vendas)
    total_despesas = sum(l.valor for l in lancs if l.tipo == 'saida')
    saldo_final = saldo_inicial + total_vendas - total_despesas
    formas = {}
    for v in vendas:
        formas[v.forma_pagamento] = formas.get(v.forma_pagamento, 0) + v.total
    contagem = {}
    for v in vendas:
        if v.itens:
            try:
                items = json.loads(v.itens)
                for it in items:
                    nome = it.get('nome','').lower()
                    qtd = int(it.get('qtd',1) or 1)
                    if nome:
                        contagem[nome] = contagem.get(nome,0) + qtd
            except Exception:
                pass
    top = sorted(contagem.items(), key=lambda x: x[1], reverse=True)[:10]
    despesas = [l for l in lancs if l.tipo == 'saida']
    meses = sorted(set(c.data[:7] for c in caixas))
    comparativo = []
    for mes in meses:
        caixas_mes = [c for c in caixas if c.data.startswith(mes)]
        vendas_mes = sum(sum(v.total for v in Venda.query.filter_by(data=c.data)) for c in caixas_mes)
        despesas_mes = sum(sum(l.valor for l in Lancamento.query.filter_by(data=c.data) if l.tipo == 'saida') for c in caixas_mes)
        comparativo.append({'mes': mes, 'vendas': vendas_mes, 'despesas': despesas_mes, 'lucro': vendas_mes - despesas_mes})
    return render_template('relatorios.html',
                           saldo_inicial=saldo_inicial,
                           total_vendas=total_vendas,
                           total_despesas=total_despesas,
                           saldo_final=saldo_final,
                           vendas_por_forma=formas,
                           top_produtos=top,
                           despesas=despesas,
                           comparativo=comparativo)

@app.route('/relatorios/pdf', methods=['POST'])
@login_required
def gerar_pdf():
    from xhtml2pdf import pisa
    html = request.form.get('html','')
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)
    result.seek(0)
    return send_file(result, download_name='relatorio.pdf', as_attachment=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(nome='HGMOTO').first():
            user = Usuario(nome='HGMOTO', senha='hgmotopecas2025')
            db.session.add(user)
            db.session.commit()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
