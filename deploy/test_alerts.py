# -*- coding: utf-8 -*-
"""
Teste de alertas - confirma que o email esta funcionando.
Uso: python deploy/test_alerts.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "alerts"))
from alert_manager import AlertManager


if __name__ == "__main__":
    sender   = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    recip    = os.getenv("EMAIL_RECIPIENTS")

    print("=" * 50)
    print("  Teste de Alertas - ML System")
    print("=" * 50)
    print("  Remetente   : {}".format(sender))
    print("  Destinatario: {}".format(recip))
    print("  Senha       : {}".format("Configurada" if password else "NAO configurada"))

    if not password:
        print("\n[ERRO] Configure EMAIL_PASSWORD no .env")
        print("  Gere em: https://myaccount.google.com/apppasswords")
        sys.exit(1)

    print("\nEnviando email de teste...")
    alert = AlertManager()
    result = alert.send_all(
        subject="[ML] Teste de Alerta - Amazon Recommender",
        message=(
            "Email de teste do sistema de alertas.\n\n"
            "Sistema : Amazon Product Recommendation\n"
            "Projeto : samara-a2d79\n"
            "Dataset : amazon_reviews\n"
            "Modelos : KNN + NCF\n\n"
            "Eventos que geram alertas:\n"
            "  - Retreinamento concluido / falhou\n"
            "  - Degradacao do modelo detectada\n"
            "  - Previsoes em lote concluidas\n"
            "  - Qualidade dos dados\n"
            "  - Deploy concluido / falhou\n"
        ),
    )

    if result["email"]:
        print("\n[OK] Email enviado com sucesso!")
        print("     Verifique: {}".format(recip))
    else:
        print("\n[ERRO] Falha ao enviar. Verifique:")
        print("  1. EMAIL_PASSWORD deve ser SENHA DE APP (16 caracteres)")
        print("     Gere em: https://myaccount.google.com/apppasswords")
        print("  2. Verificacao em 2 etapas deve estar ativa")
