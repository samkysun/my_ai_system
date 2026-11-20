-- ============================================================
-- 看板 / 存档 / 审计日志 三张表
-- 在 Supabase → SQL Editor 里整段执行一次
-- ============================================================

-- ① AI 看板
create table if not exists public.ai_board (
  id          bigserial primary key,
  source      text        not null,
  title       text        not null,
  content     text        not null,
  updated_at  timestamptz not null default now(),
  unique (source, title)
);

-- ② 推演存档
create table if not exists public.ai_pred_archive (
  id          bigserial primary key,
  period      text        not null,
  ball        text        not null,
  order_type  text        default '',
  nums        jsonb       default '[]'::jsonb,
  ts          text        default '',
  sig         text        default '',
  psig        text        default '',
  history     jsonb       default '[]'::jsonb,
  updated_at  timestamptz not null default now(),
  unique (period, ball, order_type)
);

-- ③ 审计日志
create table if not exists public.ai_audit_log (
  id      bigserial primary key,
  ts      text,
  "user"  text,
  action  text,
  detail  text,
  sig     text
);

-- 统一开权限（应用用 anon key 访问）
alter table public.ai_board          enable row level security;
alter table public.ai_pred_archive   enable row level security;
alter table public.ai_audit_log      enable row level security;

drop policy if exists "ai_board_all" on public.ai_board;
create policy "ai_board_all" on public.ai_board
  for all using (true) with check (true);

drop policy if exists "ai_pred_archive_all" on public.ai_pred_archive;
create policy "ai_pred_archive_all" on public.ai_pred_archive
  for all using (true) with check (true);

drop policy if exists "ai_audit_log_all" on public.ai_audit_log;
create policy "ai_audit_log_all" on public.ai_audit_log
  for all using (true) with check (true);
