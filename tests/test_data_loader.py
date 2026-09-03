import unittest
import pandas as pd

from data_loader import apply_filters, process_dataframe
from utils.demo_data import generate_demo_cobom_data
from visualizations import plot_hourly_weekday_heatmap, plot_resource_concentration


class TestDataLoader(unittest.TestCase):
    def test_process_dataframe_generates_derived_columns(self):
        raw_df = pd.DataFrame({
            "chamada_numero": ["CH-001", "CH-002"],
            "data_hora_criacao": ["01/06/2024 10:30:00", "02/06/2024 15:45:00"],
            "Chamada_atendimentos.local_do_fato": [
                "AV AMAZONAS, 100 - BELO HORIZONTE",
                "RUA DAS FLORES, 50 - CONTAGEM",
            ],
            "Chamada_atendimentos.local_latitude": ["-19,9167", "-19.9320"],
            "Chamada_atendimentos.local_longitude": ["-43,9345", "-44.0539"],
            "data_hora_situacao_atual": ["01/06/2024 11:30:00", "02/06/2024 16:15:00"],
        })

        processed = process_dataframe(raw_df)
        self.assertIn("chamada_data_inclusao", processed.columns)
        self.assertIn("ano", processed.columns)
        self.assertIn("mes", processed.columns)
        self.assertIn("hora", processed.columns)
        self.assertIn("dia_semana", processed.columns)
        self.assertIn("Chamada_atendimentos.local_municipio_nome", processed.columns)

        self.assertEqual(processed["hora"].iloc[0], 10)
        self.assertEqual(processed["hora"].iloc[1], 15)
        self.assertEqual(processed["Chamada_atendimentos.local_municipio_nome"].iloc[0], "BELO HORIZONTE")
        self.assertEqual(processed["Chamada_atendimentos.local_municipio_nome"].iloc[1], "CONTAGEM")
        self.assertAlmostEqual(processed["Chamada_atendimentos.local_latitude"].iloc[0], -19.9167, places=4)

    def test_filter_by_municipality(self):
        df = pd.DataFrame({
            "Chamada_atendimentos.local_municipio_nome": ["BELO HORIZONTE", "CONTAGEM", "BELO HORIZONTE"],
            "Chamada_atendimentos.natureza_descricao": ["INCENDIO", "SALVAMENTO", "INCENDIO"],
            "Empenhos.recurso_codigo_prefixo": ["ABT-102 / UR-201", "UR-201", "ABS-301"],
        })
        filtered = apply_filters(df, {
            "Chamada_atendimentos.local_municipio_nome": ["BELO HORIZONTE"]
        })
        self.assertEqual(len(filtered), 2)
        self.assertEqual(set(filtered["Chamada_atendimentos.local_municipio_nome"]), {"BELO HORIZONTE"})

    def test_filter_by_resource_prefix(self):
        df = pd.DataFrame({
            "Chamada_atendimentos.local_municipio_nome": ["BELO HORIZONTE", "CONTAGEM", "BELO HORIZONTE"],
            "Chamada_atendimentos.natureza_descricao": ["INCENDIO", "SALVAMENTO", "INCENDIO"],
            "Empenhos.recurso_codigo_prefixo": ["ABT-102 / UR-201", "UR-201", "ABS-301"],
        })
        filtered = apply_filters(df, {
            "Empenhos.recurso_codigo_prefixo": ["ABT-102"]
        })
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered["Chamada_atendimentos.local_municipio_nome"].iloc[0], "BELO HORIZONTE")

    def test_generate_demo_cobom_data(self):
        demo = generate_demo_cobom_data(50)
        self.assertEqual(len(demo), 50)
        self.assertIn("chamada_numero", demo.columns)
        self.assertIn("Chamada_atendimentos.natureza_descricao", demo.columns)

        processed = process_dataframe(demo)
        self.assertEqual(len(processed), 50)

        heatmap_fig = plot_hourly_weekday_heatmap(processed)
        self.assertIsNotNone(heatmap_fig)

        conc_fig = plot_resource_concentration(processed)
        self.assertIsNotNone(conc_fig)


if __name__ == "__main__":
    unittest.main()
