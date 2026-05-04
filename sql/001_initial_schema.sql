-- 부동산 매매·전월세 모니터링 시스템
-- 4 테이블: sale_records, rent_records, alert_rules, alerts_sent

CREATE TABLE IF NOT EXISTS sale_records (
  id              text PRIMARY KEY,
  apt_seq         text NOT NULL,
  apt_name        text,
  umd_nm          text,
  umd_cd          text,
  sgg_cd          text NOT NULL,
  jibun           text,
  road_address    text,
  deal_date       date NOT NULL,
  price_만원      integer NOT NULL,
  area            numeric(6,2) NOT NULL,
  size_label      text,
  floor           integer,
  build_year      integer,
  dealing_type    text,
  buyer_type      text,
  seller_type     text,
  agent_sgg_name  text,
  is_land_lease   boolean,
  cancel_date     date,
  cancel_type     text,
  register_date   date,
  fetched_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sale_apt_seq_date ON sale_records (apt_seq, deal_date DESC);
CREATE INDEX IF NOT EXISTS idx_sale_sgg_date     ON sale_records (sgg_cd, deal_date DESC);
CREATE INDEX IF NOT EXISTS idx_sale_size_price   ON sale_records (size_label, price_만원);

CREATE TABLE IF NOT EXISTS rent_records (
  id                    text PRIMARY KEY,
  apt_seq               text NOT NULL,
  apt_name              text,
  umd_nm                text,
  sgg_cd                text NOT NULL,
  contract_date         date NOT NULL,
  deposit_만원          integer NOT NULL,
  monthly_rent_만원     integer NOT NULL,
  area                  numeric(6,2) NOT NULL,
  size_label            text,
  floor                 integer,
  build_year            integer,
  contract_type         text,
  contract_term         text,
  pre_deposit_만원      integer,
  pre_monthly_rent_만원 integer,
  used_renewal_right    boolean,
  fetched_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rent_apt_seq_date ON rent_records (apt_seq, contract_date DESC);
CREATE INDEX IF NOT EXISTS idx_rent_sgg_date     ON rent_records (sgg_cd, contract_date DESC);

CREATE TABLE IF NOT EXISTS alert_rules (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  apt_seq           text NOT NULL,
  display_name      text NOT NULL,
  size_label        text NOT NULL,
  max_price_만원    integer,
  min_jeonse_ratio  numeric(4,3),
  enabled           boolean DEFAULT true,
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  CONSTRAINT alert_rules_apt_size_unique UNIQUE (apt_seq, size_label)
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules (enabled) WHERE enabled = true;

CREATE TABLE IF NOT EXISTS alerts_sent (
  rule_id     uuid NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
  dedup_key   text NOT NULL,
  alert_type  text NOT NULL,
  sent_at     timestamptz DEFAULT now(),
  PRIMARY KEY (rule_id, dedup_key)
);
