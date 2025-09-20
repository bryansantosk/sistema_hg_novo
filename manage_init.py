# manage_init.py
# Roda no Render durante o build para garantir tabelas e usuário padrão.

from app import app, db, Usuario

if __name__ == "__main__":
    with app.app_context():
        # cria todas as tabelas se ainda não existirem
        db.create_all()

        # garante o usuário de login do SISTEMA (tela de login do site)
        if not Usuario.query.filter_by(nome="HGMOTO").first():
            db.session.add(Usuario(nome="HGMOTO", senha="hgmotopecas2025"))
            db.session.commit()

        print("INIT OK: tabelas criadas e usuário padrão pronto", flush=True)
