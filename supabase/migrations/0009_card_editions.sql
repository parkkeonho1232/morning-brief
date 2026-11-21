-- 하루 3번(아침·16시·20시) 만든 카드를 회차별로 따로 보관한다. 이전 회차 카드는 지우지 않는다.
alter table card add column if not exists edition text not null default '아침';

-- 이미 오후 업데이트로 덮어쓴 날짜는 가장 늦은 회차로 표시해 둔다 (그날 아침 카드는 복구할 수 없음)
update card c set edition = x.e
from (select base_date, max(body->>'edition') as e from card
      where body ? 'edition' group by base_date) x
where c.base_date = x.base_date;

alter table card drop constraint if exists card_base_date_kind_rank_key;
alter table card add constraint card_base_date_edition_kind_rank_key unique (base_date, edition, kind, rank);
