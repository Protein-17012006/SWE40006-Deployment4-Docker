-- Quick Poll 1.0.0 schema
CREATE TABLE polls (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug       varchar(12)  NOT NULL UNIQUE,
    question   varchar(200) NOT NULL,
    created_at timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE options (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    poll_id  bigint      NOT NULL REFERENCES polls (id) ON DELETE CASCADE,
    position smallint    NOT NULL,
    label    varchar(80) NOT NULL,
    UNIQUE (poll_id, position),
    UNIQUE (id, poll_id)
);

-- The composite foreign key guarantees that a vote's option belongs to the poll being voted on.
CREATE TABLE votes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    poll_id    bigint      NOT NULL,
    option_id  bigint      NOT NULL,
    voter_id   uuid        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (poll_id, voter_id),
    FOREIGN KEY (option_id, poll_id) REFERENCES options (id, poll_id) ON DELETE CASCADE
);

CREATE INDEX votes_option_id_idx ON votes (option_id);
