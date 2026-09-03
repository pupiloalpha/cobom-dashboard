"""Gerador de dados sintéticos de demonstração do COBOM-BH / CBMMG."""

import datetime
import numpy as np
import pandas as pd


def generate_demo_cobom_data(num_records: int = 1500, random_seed: int = 42) -> pd.DataFrame:
    """Gera um DataFrame com dados fictícios porém estruturalmente idênticos aos do CAD/COBOM."""
    np.random.seed(random_seed)

    municipalities_data = [
        {"nome": "BELO HORIZONTE", "lat": -19.9167, "lon": -43.9345, "weight": 0.55},
        {"nome": "CONTAGEM", "lat": -19.9320, "lon": -44.0539, "weight": 0.18},
        {"nome": "BETIM", "lat": -19.9678, "lon": -44.1983, "weight": 0.12},
        {"nome": "NOVA LIMA", "lat": -19.9856, "lon": -43.8468, "weight": 0.05},
        {"nome": "SANTA LUZIA", "lat": -19.7697, "lon": -43.8514, "weight": 0.04},
        {"nome": "SABARA", "lat": -19.8906, "lon": -43.8058, "weight": 0.03},
        {"nome": "IBIRITE", "lat": -20.0219, "lon": -44.0594, "weight": 0.03},
    ]

    muni_names = [m["nome"] for m in municipalities_data]
    muni_weights = np.array([m["weight"] for m in municipalities_data])
    muni_weights = muni_weights / muni_weights.sum()

    naturezas = [
        ("INCENDIO EM VEGETACAO", 0.22),
        ("ACIDENTE DE TRANSITO COM VITIMA", 0.20),
        ("SALVAMENTO DE PESSOA EM LOCAL DE RISCO", 0.14),
        ("INCENDIO EM EDIFICACAO RESIDENCIAL", 0.10),
        ("CAPTURA / CONTENCAO DE ANIMAL", 0.12),
        ("QUEDA DE ARVORE EM VIA PUBLICA", 0.08),
        ("ATENDIMENTO PRE-HOSPITALAR (APH)", 0.08),
        ("VAZAMENTO DE GAS GLP", 0.04),
        ("DESABAMENTO OU COLAPSO DE ESTRUTURA", 0.02),
    ]
    nat_names = [n[0] for n in naturezas]
    nat_weights = np.array([n[1] for n in naturezas])
    nat_weights = nat_weights / nat_weights.sum()

    units_data = [
        "1º BBM / 1ª CIA (SAVASSI - BH)",
        "1º BBM / 2ª CIA (CENTRO - BH)",
        "1º BBM / 3ª CIA (PAMPULHA - BH)",
        "2º BBM / 1ª CIA (CONTAGEM)",
        "2º BBM / 2ª CIA (BETIM)",
        "3º BBM / 1ª CIA (VENDA NOVA - BH)",
        "3º BBM / 2ª CIA (SANTA LUZIA)",
        "COBOM / OPERACOES ESPECIAIS (BEMAD)",
    ]

    classificacoes = [
        ("EMERGENCIA", 0.50),
        ("URGENCIA", 0.35),
        ("PRIORIDADE BAIXA", 0.12),
        ("TROTE / CANCELADA", 0.03),
    ]
    class_names = [c[0] for c in classificacoes]
    class_weights = np.array([c[1] for c in classificacoes])
    class_weights = class_weights / class_weights.sum()

    recursos_pool = ["ABT-102", "ABT-105", "UR-201", "UR-204", "ABS-301", "ACA-401", "AR-501", "VP-601", "MOB-01"]

    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=365)
    seconds_range = int((end_date - start_date).total_seconds())

    raw_hour_probs = np.array([
        0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06,
        0.07, 0.07, 0.06, 0.06, 0.07, 0.08, 0.08, 0.08, 0.07, 0.05,
        0.03, 0.02, 0.01, 0.01,
    ])
    hour_probs = raw_hour_probs / raw_hour_probs.sum()

    num_vtr_probs = np.array([0.70, 0.22, 0.08])
    num_vtr_probs = num_vtr_probs / num_vtr_probs.sum()

    rows = []
    for i in range(num_records):
        call_num = f"2026-CH-{100000 + i}"
        reds_num = f"2026-00{200000 + i}-001" if np.random.rand() > 0.15 else ""

        random_sec = np.random.randint(0, seconds_range)
        created_dt = start_date + datetime.timedelta(seconds=random_sec)

        hour_prob = np.random.choice(range(24), p=hour_probs)
        created_dt = created_dt.replace(hour=hour_prob, minute=np.random.randint(0, 60), second=np.random.randint(0, 60))

        muni_idx = np.random.choice(len(muni_names), p=muni_weights)
        muni_info = municipalities_data[muni_idx]
        muni_name = muni_info["nome"]
        lat = float(muni_info["lat"] + np.random.normal(0, 0.035))
        lon = float(muni_info["lon"] + np.random.normal(0, 0.035))

        natureza = np.random.choice(nat_names, p=nat_weights)
        classificacao = np.random.choice(class_names, p=class_weights)

        if "CONTAGEM" in muni_name or "BETIM" in muni_name or "IBIRITE" in muni_name:
            unidade = np.random.choice(["2º BBM / 1ª CIA (CONTAGEM)", "2º BBM / 2ª CIA (BETIM)"])
        elif "SANTA LUZIA" in muni_name or "SABARA" in muni_name:
            unidade = np.random.choice(["3º BBM / 1ª CIA (VENDA NOVA - BH)", "3º BBM / 2ª CIA (SANTA LUZIA)"])
        else:
            unidade = np.random.choice(units_data[:4] + [units_data[-1]])

        num_vtr = np.random.choice([1, 2, 3], p=num_vtr_probs)
        vtrs = np.random.choice(recursos_pool, size=num_vtr, replace=False)
        recurso_str = " / ".join(vtrs)

        duration_min = max(5, int(np.random.exponential(scale=65)))
        finished_dt = created_dt + datetime.timedelta(minutes=duration_min)

        logradouro = f"AVENIDA PRINCIPAL Nº {np.random.randint(10, 5000)} - {muni_name}"

        rows.append({
            "chamada_numero": call_num,
            "reds": reds_num,
            "data_hora_criacao": created_dt.strftime("%d/%m/%Y %H:%M:%S"),
            "hora_criacao": created_dt.strftime("%H:%M:%S"),
            "Chamada_atendimentos.local_do_fato": logradouro,
            "Chamada_atendimentos.local_latitude": lat,
            "Chamada_atendimentos.local_longitude": lon,
            "Chamada_atendimentos.natureza_codigo": f"N{np.random.randint(100, 999)}",
            "Chamada_atendimentos.natureza_descricao": natureza,
            "Chamada_atendimentos.unidade_servico_codigo": f"U{np.random.randint(10, 99)}",
            "Chamada_atendimentos.unidade_servico_nome": unidade,
            "Empenhos.recurso_codigo_prefixo": recurso_str,
            "Chamada_atendimentos.chamada_classificacao_descricao": classificacao,
            "data_classificacao": finished_dt.strftime("%d/%m/%Y"),
            "hora_classificacao": finished_dt.strftime("%H:%M:%S"),
            "estado_chamada": "ENCERRADA",
            "Chamada_atendimentos.local_municipio_id": muni_idx + 1,
            "Chamada_atendimentos.local_municipio_nome": muni_name,
            "data_hora_situacao_atual": finished_dt.strftime("%d/%m/%Y %H:%M:%S"),
        })

    return pd.DataFrame(rows)
