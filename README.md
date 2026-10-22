# AgroSan - Controle de Manejo Sanitário e Vacinação

Sistema acadêmico Flask para lotes, animais, vacinações e manejos sanitários. Os históricos ficam vinculados ao animal; exclusões de registros com dependências são bloqueadas. Fabricante, lote da vacina, dose, observações e carência são persistidos.

## Executar no Windows

Requer Python 3.12 ou superior. No terminal, dentro desta pasta:

```powershell
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m flask --app app init-db
.venv/Scripts/waitress-serve.exe --listen=127.0.0.1:5001 app:app
```

Acesse http://127.0.0.1:5001. Clique em **Criar minha conta**, escolha usuário e senha e confirme a senha. Em uma instalação vazia, a primeira conta será administradora. As próximas contas públicas serão operadoras, sem permissão para excluir ou administrar usuários. Não há senha padrão. O cadastro usa o mesmo ambiente compartilhado da propriedade, sem separação de dados por conta. Senhas exigem pelo menos 12 caracteres, maiúscula, minúscula, número e símbolo. Para criar um operador: `create-user --perfil app_user`. Nas próximas execuções, use `./iniciar.ps1`. Para trocar uma senha, use `flask --app app set-password --username admin` com o Python da `.venv`. No PostgreSQL, execute esse comando administrativo com a conta proprietária do banco.

O SQLite local é criado em `instance/agrosan.db`; a chave da sessão é aleatória e persistida em `instance/.secret_key`. Ambos são ignorados pelo Git. `init-db` não apaga dados. Não execute o SQL antigo sobre o banco novo.

## Importar o banco recebido

Antes de cadastrar novos registros de negócio:

```powershell
.venv/Scripts/python.exe -m flask --app app import-legacy database.db
```

A importação abre a origem somente para leitura e só aceita destino vazio de lotes, animais, vacinações e manejos. Em caso de erro, cancela a transação inteira. As contas antigas não são importadas: crie credenciais novas. A vacinação antiga pode gerar um animal identificado pelo texto que havia sido digitado. Campos ausentes são marcados como não informados; dose, fabricante e observações que o sistema anterior descartou não podem ser recuperados. Revise os dados importados, os vínculos dos animais aos lotes e as datas antes da entrega.

## Funcionalidades e permissões

- Administrador: todas as operações, criação de usuários e últimos 500 eventos de auditoria.
- Operador: consulta, cadastro e edição. Não pode excluir, criar usuários ou consultar logs.
- CRUD completo de lotes, animais, vacinações e manejos. As telas de edição usam PUT; exclusões usam DELETE com confirmação. Sem JavaScript a edição também funciona via formulário POST.
- Filtros de histórico por lote e por animal na página Registros.
- Alertas de doses atrasadas e de hoje no painel. Registros sem próxima dose exibem "Sem agendamento".
- Carência calculada a partir da data de aplicação/manejo e dos dias informados. Não existe recomendação automática de dose ou carência; preencha conforme o produto e a orientação responsável.
- Quantidade informada do lote é descritiva; o vínculo real de cada animal é definido em seu cadastro.

## API

Todas as rotas exigem sessão autenticada. Recursos: `lotes`, `animais`, `vacinacao`, `manejo_sanitario`.

| Método | Caminho | Resultado |
|---|---|---|
| GET | `/api/<recurso>` | Lista |
| GET | `/api/<recurso>/<id>` | Consulta |
| POST | `/api/<recurso>` | Cria (201) |
| PUT | `/api/<recurso>/<id>` | Atualiza todos os campos do formulário |
| DELETE | `/api/<recurso>/<id>` | Exclui (204), apenas administrador |

POST, PUT e DELETE exigem token CSRF no cabeçalho `X-CSRFToken` ou no campo `csrf_token`. O token está na meta `csrf-token` das páginas autenticadas. Campos e tipos estão em `agrosan/routes.py`, na definição `ENTITIES`. Erros de validação retornam 400; duplicidade ou dependências, 409; ausência de registro, 404; falta de permissão, 403. Requisições sem sessão redirecionam ao login.

## Banco de Dados II: PostgreSQL

SQLite facilita a execução local, mas não oferece papéis administrativos nem funções armazenadas SQL como os critérios do diagnóstico pedem. Use PostgreSQL para demonstrar essa disciplina. O esquema é único em `schema.sql`: o inicializador adapta apenas a sintaxe de IDs e timestamps para PostgreSQL. As relações e constraints são iguais.

1. Instale PostgreSQL 16 ou superior, incluindo `psql`, `pg_dump` e `pg_restore`.
2. Defina `AGROSAN_OWNER_PASSWORD` e `AGROSAN_APP_PASSWORD` com senhas diferentes no ambiente, sem colocá-las no Git. Execute `psql -U postgres -f sql/provision_roles.sql` uma única vez. O script cria `agrosan_owner`, `agrosan_app` e o banco `agrosan`.
3. Defina `DATABASE_URL` com a conexão de `agrosan_owner`; execute `flask --app app init-db`. Use o Python da `.venv` como nos comandos acima.
4. Execute `psql -U agrosan_owner -d agrosan -f sql/grants.sql`. As variáveis de senha do passo 2 pertencem ao script de provisionamento; o `psql` pode pedir a senha novamente.
5. Troque `DATABASE_URL` para a conexão de `agrosan_app`. Use URL encoding se a senha tiver caracteres especiais. Crie o administrador da aplicação com `create-user` e importe o legado se necessário.

O usuário de banco `agrosan_owner` administra a estrutura. `agrosan_app` executa as operações da aplicação, não cria tabelas, não altera nem apaga logs e não altera contas existentes. Os perfis admin/operador do sistema são uma camada adicional, distinta dos usuários do PostgreSQL.

A função `status_vacinacao(TEXT)` é consultada na listagem PostgreSQL. A função de gatilho `registrar_auditoria()` registra INSERT, UPDATE e DELETE nas quatro tabelas de negócio. A função roda com permissões do proprietário e caminho de esquema fixo. O SQLite também tem os 12 gatilhos correspondentes, criados efetivamente pelo inicializador.

## Backup e restauração

```powershell
.venv/Scripts/python.exe -m flask --app app backup-db
```

O destino padrão é `instance/backups/` com nome único. SQLite usa cópia consistente pela API de backup; PostgreSQL usa `pg_dump` em formato customizado e exige a ferramenta no PATH. Não sobrescreve arquivos existentes. Para rotina diária, configure o Agendador de Tarefas do Windows para executar esse comando, com esta pasta como diretório de trabalho e as mesmas variáveis de ambiente. Defina retenção e armazene também uma cópia fora da máquina.

Para restaurar SQLite, pare o servidor, guarde uma cópia do banco atual e copie o backup para o caminho `DATABASE_PATH` (padrão `instance/agrosan.db`). Para PostgreSQL, restaure em um banco novo/vazio usando `pg_restore --no-owner --no-acl -U agrosan_owner -d NOME_DO_BANCO arquivo.dump`, reaplique `sql/grants.sql` e confira os dados antes de trocar a conexão do app.

## Publicação

Use um serviço que execute Python/Waitress ou o `Dockerfile`, conectado a PostgreSQL persistente. Instalação: `pip install -r requirements.txt`. Inicialização: `waitress-serve --listen=0.0.0.0:8080 app:app`. Configure a porta 8080 no serviço. Use domínio com HTTPS e defina `APP_ENV=production`, `SECRET_KEY` aleatória de pelo menos 32 bytes e `DATABASE_URL` da conta de aplicação. Gere uma chave com `python -c "import secrets; print(secrets.token_hex(32))"`. Credenciais ficam nas variáveis do provedor.

Antes de iniciar o serviço, execute o provisionamento, `init-db`, grants e `create-user` em uma etapa administrativa com a conta proprietária. A aplicação não cria tabelas automaticamente. No serviço publicado, a chave é obrigatória e os cookies usam Secure; o acesso precisa de HTTPS. Não use SQLite em disco temporário de hospedagem. O contêiner não inclui os utilitários `pg_dump/pg_restore`; faça o backup em uma máquina administrativa com essas ferramentas ou pelo backup gerenciado do provedor.

## Segurança e verificação

Detalhes e roteiro de demonstração: [docs/entrega.md](docs/entrega.md). Testes:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
```

Para executar a mesma suíte com PostgreSQL, defina `TEST_DATABASE_URL` apontando para um banco **exclusivo de testes**, com usuário proprietário. A suíte limpa as tabelas desse banco a cada teste. Nunca use banco real nessa variável.

O `database.db` recebido foi retirado do índice Git e preservado localmente. Dados e senhas que já foram publicados continuam no histórico antigo: substitua qualquer credencial reutilizada e trate a remoção do histórico com os responsáveis pelo repositório. Não reescrevemos o histórico compartilhado.

## Repositório e organização

Repositório: https://github.com/AyramViviane/controle-de-manejo-sanitario-e-vacinacao

O README anterior apontava issues como se fossem um Project. O quadro GitHub Projects ainda precisa ser criado/vinculado por quem tem acesso; não há link de Project ou deploy confirmado. Veja a lista pronta de tarefas em [docs/kanban.md](docs/kanban.md).

## Integrantes do grupo

| Integrante | Responsabilidade original |
|---|---|
| Ayram Viviane | Alerta de vacinas e período de carência |
| Guilherme da Silva | Controle de vacinação |
| Sthefany Campos | Consulta do histórico sanitário dos lotes |

## Enviar o projeto para outra pessoa

Envie os arquivos do repositório, sem `.venv`, `.env` e `instance/` (inclui seu banco e credenciais). A pessoa precisa ter Python 3.12+ instalado e executar `iniciar.ps1` no PowerShell dentro da pasta. Na primeira execução, o script prepara o ambiente, instala as dependências e cria o banco local vazio. Depois, basta abrir http://127.0.0.1:5001 e clicar em **Criar minha conta**. A primeira conta da nova instalação será administradora.

O endereço `127.0.0.1` funciona somente na própria máquina. Para acesso remoto ao mesmo servidor, será necessária a publicação, deixada para uma próxima etapa. Novas contas em uma mesma instalação acessam os registros compartilhados dessa instalação.
# agrosan
