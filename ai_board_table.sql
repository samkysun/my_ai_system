-- ============================================================
-- AI 看板表（在 Supabase → SQL Editor 里执行一次）
-- ============================================================
create table if not exists public.ai_board (
  id          bigserial primary key,
  source      text        not null,
  title       text        not null,
  content     text        not null,
  updated_at  timestamptz not null default now(),
  unique (source, title)
);

alter table public.ai_board enable row level security;

-- 允许匿名读写（应用用 anon key 访问；如需更严可改为登录用户策略）
drop policy if exists "ai_board_all" on public.ai_board;
create policy "ai_board_all" on public.ai_board
  for all using (true) with check (true);
