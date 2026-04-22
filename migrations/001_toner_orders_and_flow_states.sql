begin;

alter table contact_flow_state
    add column if not exists customer_existed_before_flow boolean null;

alter table contact_flow_state
    drop constraint if exists chk_contact_flow_state_current_state;

alter table contact_flow_state
    add constraint chk_contact_flow_state_current_state
        check (
            current_state in (
                'awaiting_need_now',
                'awaiting_empty_pickup_no_need',
                'awaiting_empty_units_no_need',
                'awaiting_empty_type_no_need',
                'awaiting_pickup_slot_no_need',
                'awaiting_printer_brand',
                'awaiting_printer_model',
                'awaiting_toner_type',
                'awaiting_units',
                'awaiting_empty_pickup_existing_customer',
                'awaiting_empty_units_existing_customer',
                'awaiting_empty_type_existing_customer',
                'awaiting_pickup_slot_existing_customer',
                'awaiting_new_customer_data',
                'awaiting_empty_pickup_new_customer',
                'awaiting_empty_units_new_customer',
                'awaiting_empty_type_new_customer',
                'awaiting_pickup_slot_new_customer',
                'closed_no_need',
                'closed_existing_without_pickup',
                'closed_existing_with_pickup',
                'closed_new_without_pickup',
                'closed_new_with_pickup'
            )
        );

create table if not exists toner_orders (
    id bigserial primary key,
    contact_id bigint not null
        references contacts(id)
        on delete cascade,

    phone text not null,
    printer_brand text null,
    printer_model text null,
    printer_raw text null,

    toner_type text null,
    toner_units integer null,
    customer_exists boolean null,

    delivery_address text null,
    budget_email text null,
    status text not null default 'draft',

    empty_pickup_requested boolean null,
    empty_units integer null,
    empty_type text null,
    pickup_slot_text text null,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint chk_toner_orders_toner_units
        check (toner_units is null or toner_units > 0),

    constraint chk_toner_orders_empty_units
        check (empty_units is null or empty_units > 0),

    constraint chk_toner_orders_toner_type
        check (
            toner_type is null
            or toner_type in ('ecologico', 'original', 'compatible')
        ),

    constraint chk_toner_orders_empty_type
        check (
            empty_type is null
            or empty_type in ('ecologico', 'original', 'compatible')
        ),

    constraint chk_toner_orders_status
        check (
            status in ('draft', 'pending_budget', 'confirmed', 'pickup_requested', 'closed', 'cancelled')
        )
);

create index if not exists idx_toner_orders_contact_id
    on toner_orders(contact_id);

create index if not exists idx_toner_orders_phone
    on toner_orders(phone);

create index if not exists idx_toner_orders_status
    on toner_orders(status);

create trigger trg_toner_orders_updated_at
before update on toner_orders
for each row
execute function set_updated_at();

comment on table toner_orders is 'Pedidos o solicitudes del flujo de toner y recogida de vacios';

commit;
