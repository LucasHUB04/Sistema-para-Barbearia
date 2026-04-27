document.addEventListener('DOMContentLoaded', () => {

    // ==========================================
    // 1. LOGIN
    // ==========================================
    const form = document.getElementById('login-form');
    if (form) {
        // Detecta tipo fixo (loginBarbeiro.html tem data-tipo)
        const tipoFixo = form.dataset.tipo;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const senha = document.getElementById('senha').value;
            const tipo  = tipoFixo ||
                          (document.querySelector('input[name="tipo_login"]:checked')?.value || 'cliente');
            try {
                const res  = await fetch('/login-page', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, senha, tipo })
                });
                const data = await res.json();
                if (data.success) {
                    window.location.href = data.redirect || '/';
                } else if (data.pendente_pagamento) {
                    if (data.barbearia_id) {
                        window.location.href = `/pagamento/${data.barbearia_id}`;
                    } else {
                        alert('Pagamento pendente. Acesse o link de cadastro para finalizar o pagamento.');
                    }
                } else {
                    alert('Erro: ' + (data.message || 'Credenciais inválidas'));
                }
            } catch (err) { console.error('Erro login:', err); }
        });

        // Atualiza título ao trocar tipo
        document.querySelectorAll('input[name="tipo_login"]').forEach(r => {
            r.addEventListener('change', () => {
                const t = document.getElementById('login-titulo');
                const s = document.getElementById('login-subtitulo');
                if (!t) return;
                const map = {
                    barbeiro: ['Área da Barbearia', 'Acesse o painel do seu negócio'],
                    admin:    ['Painel Administrativo', 'Acesso restrito'],
                    cliente:  ['Bem-vindo de volta', 'Acesse sua conta para continuar']
                };
                const [titulo, sub] = map[r.value] || map.cliente;
                t.textContent = titulo;
                s.textContent = sub;
            });
        });

        // Aplica neon automaticamente na tela de barbeiro dedicada
        if (tipoFixo === 'barbeiro') {
            const card = document.querySelector('.login-page');
            if (card) card.classList.add('neon-ativo');
        }
    }

    // ==========================================
    // 2. CADASTRO — navegação entre steps
    // ==========================================
    window.escolherTipo  = (tipo) => mostrarStep(tipo === 'cliente' ? 'step-cliente' : 'step-barb-1');
    window.voltarStep    = (id)   => mostrarStep(id);
    window.proximoStep   = (id)   => mostrarStep(id);

    function mostrarStep(id) {
        document.querySelectorAll('.cadastro-step').forEach(s => s.classList.remove('active'));
        document.getElementById(id)?.classList.add('active');
    }

    const formCliente = document.getElementById('form-cliente');
    if (formCliente) {
        formCliente.addEventListener('submit', function(e) {
            const s = this.querySelector('[name="senha"]').value;
            const c = this.querySelector('[name="confirmar_senha"]').value;
            if (s !== c) { e.preventDefault(); alert('As senhas não coincidem.'); }
        });
    }

    window.adicionarServico = () => {
        const lista = document.getElementById('lista-servicos');
        const item  = document.createElement('div');
        item.className = 'add-item';
        item.innerHTML = `
            <input type="text" placeholder="Nome do serviço" class="inp-servico-nome">
            <input type="text" placeholder="Preço (R$)" class="inp-servico-preco" style="width:90px">
            <input type="text" placeholder="Duração (min)" class="inp-servico-dur" style="width:100px">
            <button type="button" onclick="this.parentElement.remove()" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:18px;">✕</button>`;
        lista.appendChild(item);
    };

    window.adicionarBarbeiro = () => {
        const lista = document.getElementById('lista-barbeiros');
        const item  = document.createElement('div');
        item.className = 'add-item';
        item.innerHTML = `
            <input type="text" placeholder="Nome do barbeiro" class="inp-barbeiro-nome">
            <input type="text" placeholder="Especialidade" class="inp-barbeiro-esp">
            <button type="button" onclick="this.parentElement.remove()" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:18px;">✕</button>`;
        lista.appendChild(item);
    };

    window.selecionarPlano = (plano, el) => {
        document.querySelectorAll('.plano-card').forEach(c => c.classList.remove('selecionado'));
        el.classList.add('selecionado');
        const input = document.getElementById('input-plano');
        if (input) input.value = plano;
    };

    window.finalizarCadastroBarbearia = () => {
        const dados = {
            nome:      document.getElementById('barb-nome')?.value,
            email:     document.getElementById('barb-email')?.value,
            senha:     document.getElementById('barb-senha')?.value,
            confirmar: document.getElementById('barb-confirmar')?.value,
            cnpj:      document.getElementById('barb-cnpj')?.value,
            telefone:  document.getElementById('barb-tel')?.value,
            cep:       document.getElementById('barb-cep')?.value,
            rua:       document.getElementById('barb-rua')?.value,
            numero:    document.getElementById('barb-numero')?.value,
            bairro:    document.getElementById('barb-bairro')?.value,
            cidade:    document.getElementById('barb-cidade')?.value,
            estado:    document.getElementById('barb-estado')?.value,
            plano:     document.getElementById('input-plano')?.value || 'mensal',
            metodo_pagamento: 'pix'
        };

        if (dados.senha !== dados.confirmar) { alert('As senhas não coincidem.'); return; }
        if (!dados.nome || !dados.email)      { alert('Preencha todos os campos obrigatórios.'); return; }

        const servicos = [];
        document.querySelectorAll('#lista-servicos .add-item').forEach(item => {
            const nome = item.querySelector('.inp-servico-nome')?.value;
            if (nome) servicos.push({
                nome,
                preco: item.querySelector('.inp-servico-preco')?.value || 0,
                dur:   item.querySelector('.inp-servico-dur')?.value   || 30
            });
        });

        const barbeiros = [];
        document.querySelectorAll('#lista-barbeiros .add-item').forEach(item => {
            const nome = item.querySelector('.inp-barbeiro-nome')?.value;
            if (nome) barbeiros.push({
                nome,
                esp: item.querySelector('.inp-barbeiro-esp')?.value || ''
            });
        });

        fetch('/cadastro/barbearia', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...dados, servicos, barbeiros })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                window.location.href = data.redirect;
            } else {
                alert('Erro: ' + (data.message || 'Tente novamente'));
            }
        })
        .catch(err => console.error('Erro cadastro:', err));
    };

    // ==========================================
    // 3. INDEX — Modal de agendamento
    // ==========================================
    let agendamento = {};

    window.abrirBarbearia = window.abrirModal = (id, nome, bairro, avaliacao) => {
        agendamento = { barbearia_id: id, barbearia_nome: nome };
        document.getElementById('modal-nome').textContent = nome || 'Barbearia';
        document.getElementById('modal-info').textContent = `${bairro || ''} ${avaliacao ? '• ⭐ ' + avaliacao : ''}`;
        document.getElementById('modal-logo').textContent = (nome || 'BB').substring(0, 2).toUpperCase();
        irStep(1);
        document.getElementById('modal-overlay')?.classList.add('active');
        document.getElementById('modal-agendamento')?.classList.add('active');
    };

    window.fecharModal = () => {
        document.getElementById('modal-overlay')?.classList.remove('active');
        document.getElementById('modal-agendamento')?.classList.remove('active');
    };

    window.irStep = (n) => {
        document.querySelectorAll('.modal-step').forEach((s, i) => s.classList.toggle('active', i + 1 === n));
        document.querySelectorAll('.step-item').forEach((s, i) => {
            s.classList.remove('active', 'done');
            if (i + 1 === n) s.classList.add('active');
            if (i + 1 < n)  s.classList.add('done');
        });
        if (n === 4) preencherConfirmacao();
    };

    window.selecionarServico = (el, nome, preco, duracao) => {
        document.querySelectorAll('.servico-item').forEach(s => s.classList.remove('selecionado'));
        el.classList.add('selecionado');
        agendamento.servico = nome; agendamento.preco = preco; agendamento.duracao = duracao;
        document.getElementById('btn-step-1').disabled = false;
    };

    window.selecionarBarbeiro = (el, nome, id) => {
        document.querySelectorAll('.barbeiro-item').forEach(b => b.classList.remove('selecionado'));
        el.classList.add('selecionado');
        agendamento.barbeiro = nome; agendamento.barbeiro_id = id;
        document.getElementById('btn-step-2').disabled = false;
    };

    window.carregarHorarios = () => {
        const data = document.getElementById('input-data').value;
        if (!data) return;
        agendamento.data = data;
        const grid = document.getElementById('horarios-grid');
        grid.innerHTML = '';
        const horarios = ['09:00','09:30','10:00','10:30','11:00','11:30','14:00','14:30','15:00','15:30','16:00'];
        const ocupados = ['10:00','14:30'];
        horarios.forEach(h => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'horario-btn' + (ocupados.includes(h) ? ' ocupado' : '');
            btn.textContent = h;
            btn.disabled = ocupados.includes(h);
            btn.onclick = () => {
                document.querySelectorAll('.horario-btn').forEach(b => b.classList.remove('selecionado'));
                btn.classList.add('selecionado');
                agendamento.horario = h;
                document.getElementById('btn-step-3').disabled = false;
            };
            grid.appendChild(btn);
        });
    };

    function preencherConfirmacao() {
        const fmt = d => d ? new Date(d + 'T00:00').toLocaleDateString('pt-BR', { weekday:'long', day:'2-digit', month:'long' }) : '—';
        document.getElementById('conf-barbearia').textContent = agendamento.barbearia_nome || '—';
        document.getElementById('conf-servico').textContent   = agendamento.servico   || '—';
        document.getElementById('conf-barbeiro').textContent  = agendamento.barbeiro  || '—';
        document.getElementById('conf-data').textContent      = fmt(agendamento.data);
        document.getElementById('conf-horario').textContent   = agendamento.horario   || '—';
        document.getElementById('conf-preco').textContent     = agendamento.preco ? 'R$ ' + agendamento.preco : '—';
    }

    window.confirmarAgendamento = () => {
        if (!agendamento.data || !agendamento.horario) { alert('Preencha todos os dados.'); return; }

        // Se não logado, exibe prompt de login
        if (typeof USUARIO_LOGADO !== 'undefined' && !USUARIO_LOGADO) {
            fecharModal();
            document.getElementById('modal-login-overlay')?.classList.add('active');
            document.getElementById('modal-login-prompt')?.classList.add('active');
            return;
        }

        fetch('/agendar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(agendamento)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                fecharModal();
                alert('Agendamento confirmado! ✅');
            } else if (data.precisa_login) {
                fecharModal();
                document.getElementById('modal-login-overlay')?.classList.add('active');
                document.getElementById('modal-login-prompt')?.classList.add('active');
            } else {
                alert('Erro: ' + (data.message || 'Tente novamente'));
            }
        });
    };

    window.fecharModalLogin = () => {
        document.getElementById('modal-login-overlay')?.classList.remove('active');
        document.getElementById('modal-login-prompt')?.classList.remove('active');
    };

    // ==========================================
    // 4. PAINEL MEUS AGENDAMENTOS
    // ==========================================
    document.getElementById('btn-meus-agendamentos')?.addEventListener('click', (e) => {
        e.preventDefault();
        const painel = document.getElementById('painel-agendamentos');
        painel?.classList.add('active');
        carregarMeusAgendamentos();
    });

    window.fecharPainelAgendamentos = () => {
        document.getElementById('painel-agendamentos')?.classList.remove('active');
    };

    function carregarMeusAgendamentos() {
        fetch('/meus-agendamentos')
        .then(r => r.json())
        .then(ags => {
            const lista = document.getElementById('agendamentos-lista');
            if (!lista) return;
            if (!ags.length) {
                lista.innerHTML = '<p class="vazio-msg" style="padding:24px;text-align:center;">Nenhum agendamento encontrado.</p>';
                return;
            }
            lista.innerHTML = ags.map(ag => `
                <div class="agendamento-item">
                    <div class="ag-status ag-${ag.status}">${ag.status}</div>
                    <div class="ag-info">
                        <strong>${ag.barbearia_nome || 'Barbearia'}</strong>
                        <p>${ag.servico} • ${ag.barbeiro}</p>
                        <p>${ag.data} • ${ag.horario}</p>
                        ${ag.rua ? `<p class="ag-local">📍 ${ag.rua}, ${ag.numero} — ${ag.bairro}</p>` : ''}
                    </div>
                    <div class="ag-acoes">
                        <button class="btn-editar-ag" onclick="abrirModalEditar(${ag.id},'${ag.data}','${ag.horario}','${ag.servico}','${ag.barbeiro}')">Editar</button>
                        <button class="btn-cancelar-ag" onclick="cancelarAgendamento(${ag.id})">Cancelar</button>
                    </div>
                </div>
            `).join('');
        });
    }

    window.cancelarAgendamento = (id) => {
        if (!confirm('Cancelar este agendamento?')) return;
        fetch(`/agendamento/cancelar/${id}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => { if (data.success) carregarMeusAgendamentos(); });
    };

    // ==========================================
    // 5. EDITAR AGENDAMENTO
    // ==========================================
    window.abrirModalEditar = (id, data, horario, servico, barbeiro) => {
        document.getElementById('edit-ag-id').value     = id;
        document.getElementById('edit-data').value      = data;
        document.getElementById('edit-horario').value   = horario;
        document.getElementById('edit-servico').value   = servico;
        document.getElementById('edit-barbeiro').value  = barbeiro;
        document.getElementById('modal-edit-overlay')?.classList.add('active');
        document.getElementById('modal-editar')?.classList.add('active');
    };

    window.fecharModalEditar = () => {
        document.getElementById('modal-edit-overlay')?.classList.remove('active');
        document.getElementById('modal-editar')?.classList.remove('active');
    };

    window.salvarEdicaoAgendamento = () => {
        const id = document.getElementById('edit-ag-id').value;
        const dados = {
            data:     document.getElementById('edit-data').value,
            horario:  document.getElementById('edit-horario').value,
            servico:  document.getElementById('edit-servico').value,
            barbeiro: document.getElementById('edit-barbeiro').value
        };
        fetch(`/agendamento/editar/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                fecharModalEditar();
                carregarMeusAgendamentos();
                alert('Agendamento atualizado! ✅');
            } else {
                alert('Erro: ' + (data.message || 'Tente novamente'));
            }
        });
    };

    // ==========================================
    // 6. MEUS DADOS (perfil do cliente)
    // ==========================================
    document.getElementById('btn-meus-dados')?.addEventListener('click', (e) => {
        e.preventDefault();
        fetch('/perfil').then(r => r.json()).then(user => {
            document.getElementById('dados-nome').value      = user.nome || '';
            document.getElementById('dados-telefone').value  = user.telefone || '';
            document.getElementById('dados-senha-atual').value = '';
            document.getElementById('dados-nova-senha').value  = '';
            document.getElementById('dropdown-perfil')?.classList.remove('active');
            document.getElementById('modal-dados-overlay')?.classList.add('active');
            document.getElementById('modal-meus-dados')?.classList.add('active');
        });
    });

    window.fecharModalDados = () => {
        document.getElementById('modal-dados-overlay')?.classList.remove('active');
        document.getElementById('modal-meus-dados')?.classList.remove('active');
    };

    window.salvarMeusDados = () => {
        const dados = {
            nome:        document.getElementById('dados-nome').value,
            telefone:    document.getElementById('dados-telefone').value,
            senha_atual: document.getElementById('dados-senha-atual').value,
            nova_senha:  document.getElementById('dados-nova-senha').value
        };
        fetch('/perfil/atualizar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                fecharModalDados();
                alert('Dados atualizados! ✅');
                if (dados.nome) document.getElementById('nav-nome-usuario').textContent = dados.nome;
            } else {
                alert('Erro: ' + (data.message || 'Verifique os dados.'));
            }
        });
    };

    // ==========================================
    // 7. DROPDOWN PERFIL
    // ==========================================
    const btnPerfil = document.getElementById('btn-perfil');
    const dropdown  = document.getElementById('dropdown-perfil');
    if (btnPerfil && dropdown) {
        btnPerfil.addEventListener('click', (e) => {
            e.preventDefault();
            dropdown.classList.toggle('active');
            e.stopPropagation();
        });
        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target) && !btnPerfil.contains(e.target)) {
                dropdown.classList.remove('active');
            }
        });
    }

    // ==========================================
    // 8. PAINEL BARBEARIA / ADMIN — Sidebar nav
    // ==========================================
    document.querySelectorAll('.nav-item[data-section]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const sec = item.dataset.section;
            if (sec === 'sair') { window.location.href = '/sair'; return; }
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            document.querySelectorAll('.painel-section').forEach(s => s.classList.remove('active'));
            document.getElementById('section-' + sec)?.classList.add('active');
            // Carrega atendimentos finalizados ao entrar na aba
            if (sec === 'atendimento') carregarAtendimentosFinalizados();
        });
    });

    function carregarAtendimentosFinalizados() {
        // Pode ser implementado com rota futura
        const lista = document.getElementById('lista-atendimentos-finalizados');
        if (lista && lista.querySelector('.vazio-msg')) {
            lista.innerHTML = '<p class="vazio-msg">Nenhum atendimento finalizado hoje.</p>';
        }
    }

    // ==========================================
    // 9. CLIENTES — filtro por tipo
    // ==========================================
    window.filtrarClientes = (tipo, btn) => {
        document.querySelectorAll('.cli-tab').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.cliente-card').forEach(c => {
            c.style.display = (tipo === 'todos' || c.dataset.tipo === tipo) ? '' : 'none';
        });
    };

    // ==========================================
    // 10. PLANO — cancelar
    // ==========================================
    window.cancelarPlano = () => {
        if (!confirm('Tem certeza que deseja cancelar o plano?\nSua barbearia ficará invisível na plataforma.')) return;
        fetch('/plano/cancelar', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                alert('Plano cancelado.');
                window.location.href = '/barbeiro';
            }
        });
    };

    // ==========================================
    // 11. ADMIN — bloquear/desbloquear
    // ==========================================
    window.toggleAcesso = (id, acao) => {
        const msg = acao === 'bloquear'
            ? 'A barbearia perderá acesso imediatamente.'
            : 'A barbearia terá o acesso restaurado.';
        if (!confirm(msg + '\n\nConfirmar?')) return;
        fetch(`/admin/barbearia/${id}/${acao}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => { if (data.success) location.reload(); });
    };

    // ==========================================
    // 12. ADMIN — salvar novo preço
    // ==========================================
    window.salvarNovoPrecoProposta = () => {
        const preco = document.getElementById('input-novo-preco')?.value;
        if (!preco || preco <= 0) { alert('Preço inválido.'); return; }
        if (!confirm(`Alterar para R$ ${preco}/mês e notificar assinantes?`)) return;
        fetch('/admin/plano/preco', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preco })
        })
        .then(r => r.json())
        .then(data => { alert(data.message || 'Atualizado!'); });
    };

    // ==========================================
    // 13. ADMIN — enviar notificação
    // ==========================================
    window.enviarNotificacao = () => {
        const destino  = document.getElementById('notif-destino')?.value;
        const assunto  = document.getElementById('notif-assunto')?.value?.trim();
        const mensagem = document.getElementById('notif-mensagem')?.value?.trim();
        if (!assunto || !mensagem) { alert('Preencha assunto e mensagem.'); return; }
        fetch('/admin/notificacao', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ destino, assunto, mensagem })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                alert(`Notificação enviada para ${data.qtd} barbearias!`);
                document.getElementById('notif-assunto').value  = '';
                document.getElementById('notif-mensagem').value = '';
            }
        });
    };

});