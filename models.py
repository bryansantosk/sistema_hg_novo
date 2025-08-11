from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    telefone = db.Column(db.String(20))
    endereco = db.Column(db.Text)
    observacoes = db.Column(db.Text)
    fiado = db.Column(db.Float, default=0.0)

class Peca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    preco = db.Column(db.Float, nullable=False)
    preco_compra = db.Column(db.Float, default=0.0)
    estoque = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50))

class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    data_abertura = db.Column(db.String(20), nullable=False)
    data_finalizacao = db.Column(db.String(20))
    status = db.Column(db.String(20), default='aberto')
    observacoes = db.Column(db.Text)
    cliente = db.relationship('Cliente', backref='servicos')

class ItemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'), nullable=False)
    peca_id = db.Column(db.Integer, db.ForeignKey('peca.id'), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Float, nullable=False)
    peca = db.relationship('Peca')

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    data = db.Column(db.String(10), nullable=False)
    total = db.Column(db.Float, nullable=False)
    forma_pagamento = db.Column(db.String(50))
    cliente = db.relationship('Cliente', backref='vendas')

class ItemVenda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'))
    peca_id = db.Column(db.Integer, db.ForeignKey('peca.id'), nullable=True)
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'), nullable=True)
    quantidade = db.Column(db.Integer)
    preco_unitario = db.Column(db.Float)
    desconto = db.Column(db.Float, default=0.0)

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128), nullable=False)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
