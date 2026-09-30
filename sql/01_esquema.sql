CREATE TABLE movimiento_vigente (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente text NOT NULL,
    date date NOT NULL,
    product text NOT NULL,
    type text NOT NULL,
    fund text NOT NULL,
    commercial_name text,
    amount numeric,
    description text,
    situacion text NOT NULL,
    fecha_corte date NOT NULL,
    CONSTRAINT movimiento_vigente_situacion_chk
        CHECK (situacion IN ('nuevo', 'sin_cambios')),
    CONSTRAINT movimiento_vigente_llave_uq
        UNIQUE NULLS NOT DISTINCT (
            id_cliente,
            date,
            product,
            type,
            fund,
            commercial_name,
            amount,
            description
        )
);

CREATE TABLE movimiento_historial (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente text NOT NULL,
    date date NOT NULL,
    product text NOT NULL,
    type text NOT NULL,
    fund text NOT NULL,
    commercial_name text,
    amount numeric,
    description text,
    situacion text NOT NULL,
    fecha_corte date NOT NULL,
    CONSTRAINT movimiento_historial_situacion_chk
        CHECK (situacion = 'eliminado')
);

CREATE TABLE corte_dia (
    id_cliente text NOT NULL,
    date date NOT NULL,
    product text NOT NULL,
    type text NOT NULL,
    fund text NOT NULL,
    commercial_name text,
    amount numeric,
    description text
);
