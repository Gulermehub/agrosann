# Entrega e demonstração

## O que está implementado

| Critério do diagnóstico | Evidência |
|---|---|
| GET, POST, PUT, DELETE | API comum em `agrosan/routes.py`; telas usam PUT/DELETE pelo `static/app.js` |
| Responsividade | CSS com breakpoints; tabelas têm rolagem própria |
| Feedback e validação | Mensagens nas telas; validação compartilhada com API, datas, tamanhos, números, vínculos e duplicidades |
| Organização | Fábrica de app, módulo de banco, rotas, importação e templates separados |
| Segredo, hash e SQL | Chave fora do código, scrypt via Werkzeug, queries parametrizadas e recursos SQL em lista permitida |
| Modelo lógico/físico | `modelo_banco_dados.puml` e `schema.sql` com as mesmas tabelas e campos |
| Usuários do banco | Scripts PostgreSQL de proprietário e aplicação com privilégios diferentes |
| Função armazenada | `status_vacinacao` integrada à listagem PostgreSQL |
| Trigger funcional | Auditoria das quatro tabelas em SQLite e PostgreSQL |
| Dump/backup | CLI `backup-db`, com restauração documentada |
| Mecanismos de segurança | Autenticação, autorização por perfil, CSRF, auditoria, bloqueio após 5 falhas por 15 minutos e cookies protegidos |

O bloqueio é persistido por nome de usuário, entre processos do servidor. Não equivale a um WAF ou a proteção contra ataques distribuídos. Sessões duram até 8 horas. Os logs registram ator em eventos da aplicação e registram a operação no banco também por trigger. Dados antigos e senhas padrão não são usados como credenciais novas.

## Roteiro de demonstração

1. Inicializar um banco vazio e criar administrador e operador com senhas próprias.
2. Cadastrar um lote, vincular um animal e registrar vacinação com todos os campos.
3. Cadastrar manejo e conferir seu histórico e carência na listagem.
4. Editar os quatro recursos. Nas ferramentas de rede do navegador, mostrar PUT. Excluir um registro sem dependências e mostrar DELETE.
5. Informar data inválida, próxima dose anterior, identificação duplicada e lote inexistente: conferir rejeição sem gravar dados.
6. Entrar como operador: tentar excluir via API e acessar usuários/logs; conferir 403.
7. Tentar enviar formulário sem CSRF: conferir 400. Errar senha cinco vezes e demonstrar bloqueio temporário, de preferência em uma conta de demonstração.
8. Entrar como administrador e mostrar os logs. No PostgreSQL, demonstrar `SELECT status_vacinacao(NULL);` e consultar gatilhos em `information_schema.triggers`.
9. Com a conta de banco da aplicação, demonstrar que criar tabela ou apagar auditoria é negado. Mostrar privilégios com `psql` usando `\dp`.
10. Gerar backup e restaurar em outro banco, conferindo contagens e histórico.
11. Abrir as telas em 375px e em desktop; conferir navegação, formulários e rolagem das tabelas.

## Itens que dependem da entrega externa

- Publicar em hospedagem escolhida e validar o endereço HTTPS real.
- Criar/vincular GitHub Projects, acompanhar tarefas e atualizar o README com o link real.
- Enviar as alterações ao repositório com as permissões do grupo e revisar a contribuição.
- Conferir o enunciado oficial: o PDF recebido é um diagnóstico, não substitui a rubrica completa.
- Preparar pitch, relatório, participação do grupo e envio no AVA.
- Revisar a vacinação importada e completar as informações que o sistema antigo não salvava.

Nenhum endereço publicado, quadro externo ou pontuação foi presumido como concluído.
