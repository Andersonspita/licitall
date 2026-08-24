-- Executado apenas na primeira inicialização do volume.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE DATABASE minhareceita;
CREATE DATABASE evolution;

\connect minhareceita
CREATE EXTENSION IF NOT EXISTS vector;

\connect evolution
CREATE EXTENSION IF NOT EXISTS vector;
