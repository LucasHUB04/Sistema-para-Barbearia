from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'chave_super_secreta_barberflow')

# ==========================================
# ⚙️ BANCO DE DADOS
# ==========================================

def get_db():
    conn = sqlite3.connect('barberflow.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()

    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        telefone TEXT,
        tipo TEXT DEFAULT 'cliente'
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS barbearias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cnpj TEXT,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        telefone TEXT,
        cep TEXT, rua TEXT, numero TEXT, bairro TEXT, cidade TEXT, estado TEXT,
        plano TEXT DEFAULT 'mensal',
        status TEXT DEFAULT 'pendente_pagamento',
        data_cadastro TEXT,
        data_vencimento TEXT,
        dia_cobranca INTEGER,
        logo_url TEXT
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS servicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barbearia_id INTEGER NOT NULL,
        nome TEXT, preco REAL, duracao INTEGER,
        FOREIGN KEY(barbearia_id) REFERENCES barbearias(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS barbeiros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barbearia_id INTEGER NOT NULL,
        nome TEXT, especialidade TEXT,
        FOREIGN KEY(barbearia_id) REFERENCES barbearias(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        barbearia_id INTEGER,
        servico TEXT, barbeiro TEXT,
        data TEXT, horario TEXT,
        preco REAL,
        status TEXT DEFAULT 'pendente'
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS pagamentos_plano (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barbearia_id INTEGER NOT NULL,
        valor REAL,
        metodo TEXT,
        status TEXT DEFAULT 'pendente',
        data_pagamento TEXT,
        data_vencimento TEXT,
        comprovante TEXT,
        FOREIGN KEY(barbearia_id) REFERENCES barbearias(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS historico_precos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preco_anterior REAL, preco_novo REAL,
        data TEXT, qtd_notificados INTEGER DEFAULT 0
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS notificacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assunto TEXT, mensagem TEXT,
        destino TEXT, qtd INTEGER DEFAULT 0, data TEXT
    )''')

    # Tabela de atendimentos em andamento (abrir/fechar serviço)
    conn.execute('''CREATE TABLE IF NOT EXISTS atendimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barbearia_id INTEGER NOT NULL,
        barbeiro_nome TEXT,
        cliente_nome TEXT,
        servico TEXT,
        valor REAL DEFAULT 0,
        data_inicio TEXT,
        data_fim TEXT,
        status TEXT DEFAULT 'aberto',
        agendamento_id INTEGER,
        FOREIGN KEY(barbearia_id) REFERENCES barbearias(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS config (
        chave TEXT PRIMARY KEY, valor TEXT
    )''')

    # Configs padrão
    for chave, valor in [
        ('preco_plano', '40'),
        ('pix_chave', ''),
        ('pix_nome', 'BarberFlow'),
        ('maquina_instrucoes', 'Solicite ao atendente a maquininha de cartão.')
    ]:
        existe = conn.execute("SELECT * FROM config WHERE chave = ?", (chave,)).fetchone()
        if not existe:
            conn.execute("INSERT INTO config (chave, valor) VALUES (?, ?)", (chave, valor))

    admin = conn.execute("SELECT * FROM usuarios WHERE email = 'admin@barberflow.com'").fetchone()
    if not admin:
        conn.execute(
            'INSERT INTO usuarios (nome, email, senha, tipo) VALUES (?, ?, ?, ?)',
            ('Administrador', 'admin@barberflow.com', generate_password_hash('Pandora@1511'), 'admin')
        )

    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🔧 HELPERS
# ==========================================

def get_config(conn, chave, default=''):
    row = conn.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    return row['valor'] if row else default

def get_preco_plano(conn):
    return float(get_config(conn, 'preco_plano', '40'))

def checar_plano_vencido(conn, barbearia_id):
    b = conn.execute('SELECT data_vencimento, status FROM barbearias WHERE id = ?', (barbearia_id,)).fetchone()
    if not b or b['status'] in ('bloqueado', 'pendente_pagamento'):
        return
    if b['data_vencimento']:
        venc = datetime.strptime(b['data_vencimento'], '%Y-%m-%d')
        if venc < datetime.now():
            conn.execute("UPDATE barbearias SET status = 'vencido' WHERE id = ?", (barbearia_id,))
            conn.commit()

def login_required(tipo=None):
    if 'user_id' not in session:
        return False
    if tipo and session.get('user_tipo') != tipo:
        return False
    return True

def get_metricas_barbearia(conn, barbearia_id):
    hoje = datetime.now().strftime('%Y-%m-%d')
    mes_atual = datetime.now().strftime('%Y-%m')
    primeiro_dia = datetime.now().replace(day=1)
    mes_ant = (primeiro_dia - timedelta(days=1)).strftime('%Y-%m')

    def soma(q, p):
        return conn.execute(q, p).fetchone()[0] or 0

    return {
        'receita_hoje': soma("SELECT SUM(preco) FROM agendamentos WHERE barbearia_id=? AND data=? AND status='confirmado'", (barbearia_id, hoje)),
        'receita_mes': soma("SELECT SUM(preco) FROM agendamentos WHERE barbearia_id=? AND data LIKE ? AND status='confirmado'", (barbearia_id, mes_atual+'%')),
        'receita_mes_ant': soma("SELECT SUM(preco) FROM agendamentos WHERE barbearia_id=? AND data LIKE ? AND status='confirmado'", (barbearia_id, mes_ant+'%')),
        'total_clientes': soma("SELECT COUNT(DISTINCT cliente_id) FROM agendamentos WHERE barbearia_id=?", (barbearia_id,)),
        'ticket_medio': soma("SELECT AVG(preco) FROM agendamentos WHERE barbearia_id=? AND status='confirmado'", (barbearia_id,)),
    }

# ==========================================
# 🌐 PÁGINAS
# ==========================================

@app.route('/')
def index():
    conn = get_db()
    barbearias_raw = conn.execute("SELECT * FROM barbearias WHERE status = 'ativo'").fetchall()
    barbearias = []
    for b in barbearias_raw:
        b_dict = dict(b)
        servicos = conn.execute('SELECT nome FROM servicos WHERE barbearia_id = ? LIMIT 3', (b['id'],)).fetchall()
        b_dict['servicos_resumo'] = ', '.join([s['nome'] for s in servicos]) or 'Corte, Barba'
        b_dict['avaliacao'] = '5.0'
        barbearias.append(b_dict)
    conn.close()
    return render_template('index.html',
        barbearias=barbearias,
        nome_usuario=session.get('user_nome'),
        user_tipo=session.get('user_tipo'),
        logado='user_id' in session
    )

@app.route('/cadastro')
def pagina_cadastro():
    return render_template('cadastro.html')

# ==========================================
# 🔐 LOGIN
# ==========================================

@app.route('/login-page', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template('loginPage.html')
    data = request.get_json()
    email = data.get('email', '').strip()
    senha = data.get('senha', '')
    tipo  = data.get('tipo', 'cliente')
    conn  = get_db()

    if tipo == 'barbeiro':
        user = conn.execute('SELECT * FROM barbearias WHERE email = ?', (email,)).fetchone()
        if user:
            checar_plano_vencido(conn, user['id'])
            user = conn.execute('SELECT * FROM barbearias WHERE email = ?', (email,)).fetchone()
        redirect_url = '/painel-barbearia'
    elif tipo == 'admin':
        user = conn.execute("SELECT * FROM usuarios WHERE email = ? AND tipo = 'admin'", (email,)).fetchone()
        redirect_url = '/painel-admin'
    else:
        user = conn.execute("SELECT * FROM usuarios WHERE email = ? AND tipo = 'cliente'", (email,)).fetchone()
        redirect_url = session.get('redirect_after_login', '/')

    conn.close()

    if user and check_password_hash(user['senha'], senha):
        if tipo == 'barbeiro' and user['status'] == 'pendente_pagamento':
            return jsonify({'success': False, 'pendente_pagamento': True,
                            'barbearia_id': user['id'],
                            'message': 'Pagamento pendente. Finalize o pagamento para ativar seu acesso.'})
        if tipo == 'barbeiro' and user['status'] in ('vencido', 'bloqueado'):
            return jsonify({'success': False, 'message': 'Plano vencido ou bloqueado. Acesse o painel para regularizar.'})
        session['user_id']   = user['id']
        session['user_tipo'] = tipo
        session['user_nome'] = user['nome']
        session.pop('redirect_after_login', None)
        return jsonify({'success': True, 'redirect': redirect_url})

    return jsonify({'success': False, 'message': 'E-mail ou senha incorretos.'})

# URL dedicada para barbearias (mais limpa para divulgar)
@app.route('/barbeiro', methods=['GET'])
def login_barbeiro():
    return render_template('loginBarbeiro.html')

@app.route('/sair')
def sair():
    session.clear()
    return redirect(url_for('login_page'))

# ==========================================
# 📝 CADASTRO
# ==========================================

@app.route('/cadastro/cliente', methods=['POST'])
def cadastro_cliente():
    nome     = request.form.get('nome', '').strip()
    email    = request.form.get('email', '').strip()
    senha    = request.form.get('senha', '')
    confirmar = request.form.get('confirmar_senha', '')
    telefone = request.form.get('telefone', '')

    if not nome or not email or not senha:
        return redirect(url_for('pagina_cadastro'))
    if senha != confirmar:
        return 'Senhas não coincidem. <a href="/cadastro">Voltar</a>'

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO usuarios (nome, email, senha, telefone, tipo) VALUES (?, ?, ?, ?, ?)',
            (nome, email, generate_password_hash(senha), telefone, 'cliente')
        )
        conn.commit()
        return redirect(url_for('login_page'))
    except sqlite3.IntegrityError:
        return 'E-mail já cadastrado. <a href="/cadastro">Voltar</a>'
    finally:
        conn.close()

@app.route('/cadastro/barbearia', methods=['POST'])
def cadastro_barbearia():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'})

    nome   = data.get('nome', '').strip()
    email  = data.get('email', '').strip()
    senha  = data.get('senha', '')
    metodo = data.get('metodo_pagamento', 'pix')

    if not nome or not email or not senha:
        return jsonify({'success': False, 'message': 'Preencha todos os campos obrigatórios.'})

    data_cadastro = datetime.now()
    # Acesso liberado apenas após pagamento confirmado
    # Status inicial: pendente_pagamento
    dia_cobranca = data_cadastro.day

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO barbearias
            (nome, cnpj, email, senha, telefone, cep, rua, numero, bairro, cidade, estado,
             plano, status, data_cadastro, dia_cobranca)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente_pagamento', ?, ?)
        ''', (
            nome, data.get('cnpj'), email, generate_password_hash(senha),
            data.get('telefone'), data.get('cep'), data.get('rua'), data.get('numero'),
            data.get('bairro'), data.get('cidade'), data.get('estado'),
            data.get('plano', 'mensal'),
            data_cadastro.strftime('%Y-%m-%d'),
            dia_cobranca
        ))
        barbearia_id = cursor.lastrowid

        for s in data.get('servicos', []):
            if s.get('nome'):
                cursor.execute(
                    'INSERT INTO servicos (barbearia_id, nome, preco, duracao) VALUES (?, ?, ?, ?)',
                    (barbearia_id, s['nome'], s.get('preco', 0), s.get('dur', 30))
                )
        for b in data.get('barbeiros', []):
            if b.get('nome'):
                cursor.execute(
                    'INSERT INTO barbeiros (barbearia_id, nome, especialidade) VALUES (?, ?, ?)',
                    (barbearia_id, b['nome'], b.get('esp', ''))
                )

        preco_plano = get_preco_plano(conn)
        cursor.execute('''
            INSERT INTO pagamentos_plano (barbearia_id, valor, metodo, status, data_pagamento)
            VALUES (?, ?, ?, 'pendente', ?)
        ''', (barbearia_id, preco_plano, metodo, data_cadastro.strftime('%Y-%m-%d')))

        conn.commit()
        return jsonify({'success': True, 'barbearia_id': barbearia_id, 'metodo': metodo,
                        'redirect': f'/pagamento/{barbearia_id}'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'E-mail já cadastrado!'})
    finally:
        conn.close()

# ==========================================
# 💳 PAGAMENTO DA ASSINATURA
# ==========================================

@app.route('/pagamento/<int:barbearia_id>')
def pagamento_view(barbearia_id):
    conn = get_db()
    barbearia = conn.execute('SELECT * FROM barbearias WHERE id = ?', (barbearia_id,)).fetchone()
    pagamento = conn.execute(
        "SELECT * FROM pagamentos_plano WHERE barbearia_id = ? AND status IN ('pendente', 'aguardando_confirmacao') ORDER BY id DESC LIMIT 1",
        (barbearia_id,)
    ).fetchone()
    pix_chave  = get_config(conn, 'pix_chave')
    pix_nome   = get_config(conn, 'pix_nome', 'BarberFlow')
    maquina    = get_config(conn, 'maquina_instrucoes')
    preco      = get_preco_plano(conn)
    conn.close()
    if not barbearia or not pagamento:
        return redirect(url_for('login_barbeiro'))
    return render_template('pagamento.html',
        barbearia=dict(barbearia),
        pagamento=dict(pagamento),
        pix_chave=pix_chave,
        pix_nome=pix_nome,
        maquina_instrucoes=maquina,
        preco=preco
    )

@app.route('/pagamento/confirmar-pix', methods=['POST'])
def confirmar_pix():
    """Barbearia envia comprovante — fica aguardando aprovação manual do admin"""
    data = request.get_json()
    barbearia_id = data.get('barbearia_id')
    comprovante  = data.get('comprovante', '')
    conn = get_db()
    conn.execute(
        "UPDATE pagamentos_plano SET comprovante = ?, status = 'aguardando_confirmacao' WHERE barbearia_id = ? AND status IN ('pendente', 'aguardando_confirmacao')",
        (comprovante, barbearia_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Comprovante enviado! Aguardando confirmação do admin (em até 24h).'})

@app.route('/plano/pagar', methods=['POST'])
def plano_pagar():
    if not login_required('barbeiro'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    barbearia_id = session['user_id']
    conn = get_db()
    preco = get_preco_plano(conn)
    metodo = request.get_json().get('metodo', 'pix')
    conn.execute('''
        INSERT INTO pagamentos_plano (barbearia_id, valor, metodo, status, data_pagamento)
        VALUES (?, ?, ?, 'pendente', ?)
    ''', (barbearia_id, preco, metodo, datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'redirect': f'/pagamento/{barbearia_id}'})

@app.route('/plano/cancelar', methods=['POST'])
def plano_cancelar():
    if not login_required('barbeiro'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    conn = get_db()
    conn.execute("UPDATE barbearias SET status='vencido' WHERE id=?", (session['user_id'],))
    conn.commit()
    conn.close()
    session.clear()
    return jsonify({'success': True})

# ==========================================
# 📅 AGENDAMENTOS
# ==========================================

@app.route('/agendar', methods=['POST'])
def agendar():
    if not login_required('cliente'):
        session['redirect_after_login'] = '/'
        return jsonify({'success': False, 'precisa_login': True,
                        'message': 'Crie uma conta ou faça login para agendar.'})
    data = request.get_json()
    conn = get_db()
    conn.execute('''
        INSERT INTO agendamentos (cliente_id, barbearia_id, servico, barbeiro, data, horario, preco)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], data.get('barbearia_id'), data.get('servico'),
          data.get('barbeiro'), data.get('data'), data.get('horario'), data.get('preco', 0)))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/agendamento/editar/<int:ag_id>', methods=['POST'])
def editar_agendamento(ag_id):
    if not login_required('cliente'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    conn = get_db()
    ag = conn.execute(
        'SELECT * FROM agendamentos WHERE id = ? AND cliente_id = ?',
        (ag_id, session['user_id'])
    ).fetchone()
    if not ag:
        conn.close()
        return jsonify({'success': False, 'message': 'Agendamento não encontrado.'})

    campos = {}
    if data.get('data'):     campos['data']     = data['data']
    if data.get('horario'):  campos['horario']  = data['horario']
    if data.get('servico'):  campos['servico']  = data['servico']
    if data.get('barbeiro'): campos['barbeiro'] = data['barbeiro']
    if data.get('barbearia_id'): campos['barbearia_id'] = data['barbearia_id']

    if campos:
        sets = ', '.join(f"{k} = ?" for k in campos)
        vals = list(campos.values()) + [ag_id]
        conn.execute(f"UPDATE agendamentos SET {sets} WHERE id = ?", vals)
        conn.commit()

    conn.close()
    return jsonify({'success': True})

@app.route('/agendamento/cancelar/<int:ag_id>', methods=['POST'])
def cancelar_agendamento(ag_id):
    if not login_required('cliente'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    conn = get_db()
    ag = conn.execute(
        'SELECT * FROM agendamentos WHERE id = ? AND cliente_id = ?',
        (ag_id, session['user_id'])
    ).fetchone()
    if not ag:
        conn.close()
        return jsonify({'success': False, 'message': 'Agendamento não encontrado.'})
    conn.execute("UPDATE agendamentos SET status = 'cancelado' WHERE id = ?", (ag_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/meus-agendamentos')
def meus_agendamentos():
    if not login_required('cliente'):
        return jsonify([])
    conn = get_db()
    ags = conn.execute('''
        SELECT a.*, b.nome AS barbearia_nome, b.rua, b.numero, b.bairro
        FROM agendamentos a
        LEFT JOIN barbearias b ON b.id = a.barbearia_id
        WHERE a.cliente_id = ? AND a.status != 'cancelado'
        ORDER BY a.data DESC, a.horario DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(a) for a in ags])

# ==========================================
# 👤 PERFIL DO CLIENTE
# ==========================================

@app.route('/perfil', methods=['GET'])
def perfil_cliente():
    if not login_required('cliente'):
        return redirect(url_for('login_page'))
    conn = get_db()
    user = conn.execute('SELECT id, nome, email, telefone FROM usuarios WHERE id = ?',
                        (session['user_id'],)).fetchone()
    conn.close()
    return jsonify(dict(user))

@app.route('/perfil/atualizar', methods=['POST'])
def atualizar_perfil():
    if not login_required('cliente'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    conn = get_db()
    try:
        if data.get('nova_senha'):
            user = conn.execute('SELECT senha FROM usuarios WHERE id = ?', (session['user_id'],)).fetchone()
            if not check_password_hash(user['senha'], data.get('senha_atual', '')):
                conn.close()
                return jsonify({'success': False, 'message': 'Senha atual incorreta.'})
            conn.execute("UPDATE usuarios SET senha = ? WHERE id = ?",
                         (generate_password_hash(data['nova_senha']), session['user_id']))

        campos = {}
        if data.get('nome'):     campos['nome']     = data['nome']
        if data.get('telefone'): campos['telefone'] = data['telefone']
        if campos:
            sets = ', '.join(f"{k} = ?" for k in campos)
            vals = list(campos.values()) + [session['user_id']]
            conn.execute(f"UPDATE usuarios SET {sets} WHERE id = ?", vals)
            if data.get('nome'):
                session['user_nome'] = data['nome']

        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

# ==========================================
# ✂️ PAINEL BARBEARIA
# ==========================================

@app.route('/painel-barbearia')
def painel_barbearia():
    if not login_required('barbeiro'):
        return redirect(url_for('login_barbeiro'))
    barbearia_id = session['user_id']
    conn = get_db()
    checar_plano_vencido(conn, barbearia_id)
    barbearia = conn.execute('SELECT * FROM barbearias WHERE id = ?', (barbearia_id,)).fetchone()

    metricas = get_metricas_barbearia(conn, barbearia_id)
    hoje = datetime.now().strftime('%Y-%m-%d')

    top = conn.execute('''SELECT servico, COUNT(*) AS cnt FROM agendamentos
        WHERE barbearia_id=? GROUP BY servico ORDER BY cnt DESC LIMIT 1''', (barbearia_id,)).fetchone()

    ags_hoje = conn.execute('''
        SELECT a.*, u.nome AS cliente_nome FROM agendamentos a
        LEFT JOIN usuarios u ON u.id = a.cliente_id
        WHERE a.barbearia_id = ? AND a.data = ? AND a.status != 'cancelado'
        ORDER BY a.horario''', (barbearia_id, hoje)).fetchall()

    todos_ags = conn.execute('''
        SELECT a.*, u.nome AS cliente_nome FROM agendamentos a
        LEFT JOIN usuarios u ON u.id = a.cliente_id
        WHERE a.barbearia_id = ?
        ORDER BY a.data DESC, a.horario DESC LIMIT 100''', (barbearia_id,)).fetchall()

    clientes_raw = conn.execute('''
        SELECT u.nome, u.id, COUNT(a.id) AS total_visitas,
               MAX(a.data) AS ultima_visita,
               (SELECT a2.servico FROM agendamentos a2
                WHERE a2.cliente_id = u.id AND a2.barbearia_id = ?
                GROUP BY a2.servico ORDER BY COUNT(*) DESC LIMIT 1) AS servico_favorito
        FROM agendamentos a JOIN usuarios u ON u.id = a.cliente_id
        WHERE a.barbearia_id = ? GROUP BY u.id ORDER BY total_visitas DESC
    ''', (barbearia_id, barbearia_id)).fetchall()

    clientes = []
    for c in clientes_raw:
        c_dict = dict(c)
        v = c_dict['total_visitas']
        c_dict['tipo'] = 'fiel' if v >= 5 else ('ocasional' if v >= 2 else 'novo')
        clientes.append(c_dict)

    barbeiros  = conn.execute('SELECT * FROM barbeiros WHERE barbearia_id=?', (barbearia_id,)).fetchall()
    servicos   = conn.execute('SELECT * FROM servicos WHERE barbearia_id=?', (barbearia_id,)).fetchall()

    historico = conn.execute('''
        SELECT a.data, a.servico, u.nome AS cliente, a.preco
        FROM agendamentos a LEFT JOIN usuarios u ON u.id = a.cliente_id
        WHERE a.barbearia_id=? AND a.status='confirmado'
        ORDER BY a.data DESC LIMIT 20''', (barbearia_id,)).fetchall()

    historico_plano = conn.execute(
        'SELECT * FROM pagamentos_plano WHERE barbearia_id=? ORDER BY data_pagamento DESC',
        (barbearia_id,)).fetchall()

    # Atendimentos em aberto
    atendimentos_abertos = conn.execute(
        "SELECT * FROM atendimentos WHERE barbearia_id=? AND status='aberto' ORDER BY data_inicio DESC",
        (barbearia_id,)).fetchall()

    preco_plano = get_preco_plano(conn)
    pix_chave   = get_config(conn, 'pix_chave')
    pix_nome    = get_config(conn, 'pix_nome', 'BarberFlow')
    maquina     = get_config(conn, 'maquina_instrucoes')
    conn.close()

    return render_template('painelBarbeiro.html',
        nome_barbearia        = barbearia['nome'],
        plano_ativo           = barbearia['status'] == 'ativo',
        agendamentos_hoje     = len(ags_hoje),
        receita_hoje          = f"{metricas['receita_hoje']:.2f}".replace('.', ','),
        receita_mes           = f"{metricas['receita_mes']:.2f}".replace('.', ','),
        receita_mes_ant       = f"{metricas['receita_mes_ant']:.2f}".replace('.', ','),
        total_clientes        = metricas['total_clientes'],
        ticket_medio          = f"{metricas['ticket_medio']:.2f}".replace('.', ','),
        servico_top           = top['servico'] if top else '—',
        proximos_agendamentos = [dict(a) for a in ags_hoje],
        todos_agendamentos    = [dict(a) for a in todos_ags],
        barbeiros             = [dict(b) for b in barbeiros],
        servicos              = [dict(s) for s in servicos],
        clientes              = clientes,
        historico             = [dict(h) for h in historico],
        preco_plano           = f'{preco_plano:.0f}',
        data_vencimento       = barbearia['data_vencimento'] or '—',
        historico_plano       = [dict(p) for p in historico_plano],
        atendimentos_abertos  = [dict(a) for a in atendimentos_abertos],
        pix_chave             = pix_chave,
        pix_nome              = pix_nome,
        maquina_instrucoes    = maquina,
    )

# ==========================================
# 🎯 ATENDIMENTOS (ABRIR / FECHAR SERVIÇO)
# ==========================================

@app.route('/atendimento/abrir', methods=['POST'])
def abrir_atendimento():
    if not login_required('barbeiro'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO atendimentos (barbearia_id, barbeiro_nome, cliente_nome, servico, valor, data_inicio, status, agendamento_id)
        VALUES (?, ?, ?, ?, ?, ?, 'aberto', ?)
    ''', (
        session['user_id'],
        data.get('barbeiro_nome', ''),
        data.get('cliente_nome', ''),
        data.get('servico', ''),
        data.get('valor', 0),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data.get('agendamento_id')
    ))
    atendimento_id = cursor.lastrowid
    # Se veio de um agendamento, atualiza status
    if data.get('agendamento_id'):
        conn.execute("UPDATE agendamentos SET status = 'em_andamento' WHERE id = ?",
                     (data['agendamento_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': atendimento_id})

@app.route('/atendimento/fechar/<int:at_id>', methods=['POST'])
def fechar_atendimento(at_id):
    if not login_required('barbeiro'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    conn = get_db()
    at = conn.execute(
        'SELECT * FROM atendimentos WHERE id = ? AND barbearia_id = ?',
        (at_id, session['user_id'])
    ).fetchone()
    if not at:
        conn.close()
        return jsonify({'success': False, 'message': 'Atendimento não encontrado.'})

    valor_final = data.get('valor', at['valor'])
    conn.execute('''
        UPDATE atendimentos SET status='finalizado', data_fim=?, valor=?
        WHERE id=?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), valor_final, at_id))

    # Atualiza agendamento se vinculado
    if at['agendamento_id']:
        conn.execute("UPDATE agendamentos SET status='confirmado', preco=? WHERE id=?",
                     (valor_final, at['agendamento_id']))

    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/atendimentos/ativos')
def atendimentos_ativos():
    if not login_required('barbeiro'):
        return jsonify([])
    conn = get_db()
    ats = conn.execute(
        "SELECT * FROM atendimentos WHERE barbearia_id=? AND status='aberto'",
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(a) for a in ats])

# ==========================================
# ⚙️ PAINEL ADMIN
# ==========================================

@app.route('/painel-admin')
def painel_admin():
    if not login_required('admin'):
        return redirect(url_for('login_page'))
    conn = get_db()
    barbearias = conn.execute('SELECT * FROM barbearias ORDER BY data_cadastro DESC').fetchall()
    total_ativas   = sum(1 for b in barbearias if b['status'] == 'ativo')
    total_vencidos = sum(1 for b in barbearias if b['status'] == 'vencido')
    preco_plano    = get_preco_plano(conn)

    pagamentos_pendentes = conn.execute('''
        SELECT p.*, b.nome AS barbearia_nome, b.email AS barbearia_email
        FROM pagamentos_plano p
        JOIN barbearias b ON b.id = p.barbearia_id
        WHERE p.status IN ('pendente', 'aguardando_confirmacao')
        ORDER BY p.data_pagamento DESC
    ''').fetchall()

    historico_precos = conn.execute('SELECT * FROM historico_precos ORDER BY data DESC LIMIT 20').fetchall()
    historico_notif  = conn.execute('SELECT * FROM notificacoes ORDER BY data DESC LIMIT 20').fetchall()

    pix_chave  = get_config(conn, 'pix_chave')
    pix_nome   = get_config(conn, 'pix_nome', 'BarberFlow')
    maquina    = get_config(conn, 'maquina_instrucoes')
    conn.close()

    return render_template('painelAdmin.html',
        total_ativas           = total_ativas,
        total_assinantes       = len(barbearias),
        receita_plataforma     = f'{total_ativas * preco_plano:.2f}'.replace('.', ','),
        total_vencidos         = total_vencidos,
        barbearias             = [dict(b) for b in barbearias],
        preco_plano            = int(preco_plano),
        pagamentos_pendentes   = [dict(p) for p in pagamentos_pendentes],
        historico_precos       = [dict(h) for h in historico_precos],
        historico_notif        = [dict(n) for n in historico_notif],
        pix_chave              = pix_chave,
        pix_nome               = pix_nome,
        maquina_instrucoes     = maquina,
    )

@app.route('/admin/barbearia/<int:barb_id>/<acao>', methods=['POST'])
def admin_acao_barbearia(barb_id, acao):
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    if acao not in ('bloquear', 'desbloquear'):
        return jsonify({'success': False, 'message': 'Ação inválida.'})
    status = 'bloqueado' if acao == 'bloquear' else 'ativo'
    conn = get_db()
    conn.execute('UPDATE barbearias SET status=? WHERE id=?', (status, barb_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/pagamento/<int:pag_id>/confirmar', methods=['POST'])
def admin_confirmar_pagamento(pag_id):
    """Admin confirma manualmente o pagamento — libera acesso da barbearia"""
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    conn = get_db()
    pag = conn.execute('SELECT * FROM pagamentos_plano WHERE id = ?', (pag_id,)).fetchone()
    if not pag:
        conn.close()
        return jsonify({'success': False, 'message': 'Pagamento não encontrado.'})

    # Define vencimento: 30 dias a partir de hoje
    nova_venc = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    conn.execute("UPDATE pagamentos_plano SET status='confirmado' WHERE id=?", (pag_id,))
    conn.execute("UPDATE barbearias SET status='ativo', data_vencimento=? WHERE id=?",
                 (nova_venc, pag['barbearia_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/pagamento/<int:pag_id>/rejeitar', methods=['POST'])
def admin_rejeitar_pagamento(pag_id):
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    conn = get_db()
    conn.execute("UPDATE pagamentos_plano SET status='rejeitado' WHERE id=?", (pag_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/config/pagamento', methods=['POST'])
def admin_config_pagamento():
    """Admin atualiza chave PIX e instruções da maquininha"""
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    conn = get_db()
    for chave, valor in [
        ('pix_chave', data.get('pix_chave', '')),
        ('pix_nome',  data.get('pix_nome', 'BarberFlow')),
        ('maquina_instrucoes', data.get('maquina_instrucoes', ''))
    ]:
        conn.execute("UPDATE config SET valor=? WHERE chave=?", (valor, chave))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/plano/preco', methods=['POST'])
def admin_atualizar_preco():
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data = request.get_json()
    try:
        novo_preco = float(data.get('preco', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Preço inválido.'})
    if novo_preco <= 0:
        return jsonify({'success': False, 'message': 'Preço inválido.'})
    conn = get_db()
    preco_anterior = get_preco_plano(conn)
    qtd = conn.execute("SELECT COUNT(*) AS c FROM barbearias WHERE status='ativo'").fetchone()['c']
    conn.execute("UPDATE config SET valor=? WHERE chave='preco_plano'", (str(novo_preco),))
    conn.execute('''INSERT INTO historico_precos (preco_anterior, preco_novo, data, qtd_notificados)
                    VALUES (?, ?, ?, ?)''',
                 (preco_anterior, novo_preco, datetime.now().strftime('%Y-%m-%d %H:%M'), qtd))
    conn.commit()
    conn.close()
    return jsonify({'success': True,
                    'message': f'Preço atualizado para R$ {novo_preco:.0f}. {qtd} barbearias serão notificadas.'})

@app.route('/admin/notificacao', methods=['POST'])
def admin_enviar_notificacao():
    if not login_required('admin'):
        return jsonify({'success': False, 'message': 'Não autorizado.'})
    data     = request.get_json()
    destino  = data.get('destino', 'todos')
    assunto  = data.get('assunto', '').strip()
    mensagem = data.get('mensagem', '').strip()
    if not assunto or not mensagem:
        return jsonify({'success': False, 'message': 'Preencha assunto e mensagem.'})
    filtros = {'ativos': "WHERE status='ativo'", 'vencidos': "WHERE status='vencido'", 'todos': ''}
    conn = get_db()
    barbearias = conn.execute(f"SELECT email FROM barbearias {filtros.get(destino, '')}").fetchall()
    qtd = len(barbearias)
    conn.execute('INSERT INTO notificacoes (assunto, mensagem, destino, qtd, data) VALUES (?, ?, ?, ?, ?)',
                 (assunto, mensagem, destino, qtd, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'qtd': qtd})

# Admin visualiza como cliente ou como barbearia específica
@app.route('/admin/ver-como/<modo>')
def admin_ver_como(modo):
    if not login_required('admin'):
        return redirect(url_for('login_page'))
    if modo == 'cliente':
        session['admin_ver_como'] = 'cliente'
        return redirect('/')
    elif modo == 'barbearia':
        barb_id = request.args.get('id')
        if barb_id:
            # Salva o ID real do admin ANTES de fazer o swap
            session['admin_id_original'] = session['user_id']
            session['admin_ver_como'] = 'barbearia'
            session['admin_ver_barbearia_id'] = int(barb_id)
            conn = get_db()
            b = conn.execute('SELECT * FROM barbearias WHERE id = ?', (barb_id,)).fetchone()
            conn.close()
            if b:
                session['user_id']   = b['id']
                session['user_tipo'] = 'barbeiro'
                session['user_nome'] = b['nome']
                return redirect('/painel-barbearia')
    return redirect('/painel-admin')

@app.route('/admin/voltar')
def admin_voltar():
    """Volta ao painel admin após visualizar como outro tipo"""
    session['user_tipo'] = 'admin'
    # Só restaura o user_id se tiver o original salvo (modo barbearia)
    original_id = session.pop('admin_id_original', None)
    if original_id:
        session['user_id'] = original_id
    session.pop('admin_ver_como', None)
    session.pop('admin_ver_barbearia_id', None)
    return redirect('/painel-admin')

if __name__ == '__main__':
    app.run(debug=True)