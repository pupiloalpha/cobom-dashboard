import unittest
import math
import numpy as np
import pandas as pd

from utils.helpers import (
    coluna_ou_none,
    extrair_bbm,
    extrair_fracao,
    extrair_recursos,
    normalize_column_names,
    parse_coordinate,
    parse_datetime_series,
    safe_map_text,
)


class TestHelpers(unittest.TestCase):
    def test_parse_coordinate_valid_floats(self):
        self.assertAlmostEqual(parse_coordinate(-19.9167, 90), -19.9167, places=4)
        self.assertAlmostEqual(parse_coordinate("-43.9345", 180), -43.9345, places=4)

    def test_parse_coordinate_comma_decimal(self):
        self.assertAlmostEqual(parse_coordinate("-19,9167", 90), -19.9167, places=4)
        self.assertAlmostEqual(parse_coordinate("-43,934500", 180), -43.9345, places=4)

    def test_parse_coordinate_multiple_dots(self):
        res = parse_coordinate("-19.916.700", 90)
        self.assertAlmostEqual(res, -19.9167, places=3)

    def test_parse_coordinate_invalid_values(self):
        self.assertTrue(math.isnan(parse_coordinate("invalido", 90)))
        self.assertTrue(math.isnan(parse_coordinate(None, 90)))
        self.assertTrue(math.isnan(parse_coordinate(np.nan, 90)))
        self.assertTrue(math.isnan(parse_coordinate("", 90)))

    def test_parse_coordinate_exceeding_max_abs(self):
        self.assertTrue(math.isnan(parse_coordinate(150.0, 90)))
        self.assertTrue(math.isnan(parse_coordinate(-200.0, 180)))

    def test_parse_datetime_series_mixed(self):
        series = pd.Series([
            "01/05/2024 14:30:00",
            "15/05/2024 08:15:00",
            "28/05/2024",
            "invalid_date",
            None,
        ])
        parsed = parse_datetime_series(series)
        self.assertEqual(parsed.iloc[0], pd.Timestamp("2024-05-01 14:30:00"))
        self.assertEqual(parsed.iloc[1], pd.Timestamp("2024-05-15 08:15:00"))
        self.assertEqual(parsed.iloc[2], pd.Timestamp("2024-05-28 00:00:00"))
        self.assertTrue(pd.isna(parsed.iloc[3]))
        self.assertTrue(pd.isna(parsed.iloc[4]))

    def test_extrair_bbm(self):
        self.assertEqual(extrair_bbm("1º BBM / 2ª CIA (CENTRO - BH)"), "1º BBM")
        self.assertEqual(extrair_bbm("2º BBM / 1ª CIA"), "2º BBM")
        self.assertEqual(extrair_bbm("3ª CIA IND (EXTREMA)"), "3ª CIA IND")
        self.assertEqual(extrair_bbm("OUTRO COMANDO"), "Outros")
        self.assertEqual(extrair_bbm(None), "Outros")
        self.assertEqual(extrair_bbm(np.nan), "Outros")

    def test_extrair_fracao(self):
        self.assertEqual(extrair_fracao("1º BBM / 2ª CIA (CENTRO - BH)"), "1º BBM / 2ª CIA")
        self.assertEqual(extrair_fracao(None), "Outros")
        self.assertEqual(extrair_fracao(np.nan), "Outros")

    def test_extrair_recursos(self):
        df = pd.DataFrame({
            "Empenhos.recurso_codigo_prefixo": [
                "ABT-102 / UR-201",
                "UR-201, ABS-301",
                None,
                "ABT-102",
            ]
        })
        recursos = extrair_recursos(df)
        self.assertEqual(recursos, ["ABS-301", "ABT-102", "UR-201"])

    def test_extrair_recursos_sem_coluna(self):
        df = pd.DataFrame({"outra_coluna": [1, 2]})
        self.assertEqual(extrair_recursos(df), [])

    def test_normalize_column_names(self):
        df = pd.DataFrame(columns=["Nº chamada", "Local do fato", "Natureza"])
        normalized = normalize_column_names(df)
        self.assertIn("chamada_numero", normalized.columns)
        self.assertIn("Chamada_atendimentos.local_do_fato", normalized.columns)
        self.assertIn("Chamada_atendimentos.natureza_descricao", normalized.columns)

    def test_coluna_ou_none(self):
        df = pd.DataFrame(columns=["col1", "col2"])
        self.assertEqual(coluna_ou_none(df, "inexistente", "col2", "col1"), "col2")
        self.assertIsNone(coluna_ou_none(df, "inexistente1", "inexistente2"))

    def test_safe_map_text(self):
        self.assertEqual(safe_map_text("Texto Longo", max_len=5), "Texto")
        self.assertEqual(safe_map_text(None, default="Padrao"), "Padrao")
        self.assertEqual(safe_map_text(np.nan, default="Nulo"), "Nulo")


if __name__ == "__main__":
    unittest.main()
