# -*- coding: utf-8 -*-
import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class EmailAlert:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender = os.getenv("EMAIL_SENDER", "rafaelhenriquegallo@gmail.com")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.recipients = [
            r.strip()
            for r in os.getenv("EMAIL_RECIPIENTS", "rafaelhenriquegallo@gmail.com").split(",")
            if r.strip()
        ]

    def send(self, subject: str, message: str) -> bool:
        if not self.password:
            logger.warning("EMAIL_PASSWORD nao configurado.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = "ML System <{}>".format(self.sender)
            msg["To"] = ", ".join(self.recipients)

            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            html = """
            <html>
            <body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f4f4f4;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding:30px 0;">
                    <table width="600" cellpadding="0" cellspacing="0"
                           style="background:#fff;border-radius:10px;overflow:hidden;
                                  box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                      <tr>
                        <td style="background:#FF9900;padding:25px 30px;">
                          <h2 style="color:#fff;margin:0;font-size:22px;">
                            Amazon Recommender - ML System
                          </h2>
                          <p style="color:#fff3cd;margin:5px 0 0;font-size:13px;">{now}</p>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:20px 30px 10px;">
                          <h3 style="color:#232F3E;margin:0;font-size:16px;">{subject}</h3>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:10px 30px 20px;">
                          <div style="background:#f8f9fa;border-left:4px solid #FF9900;
                                      border-radius:4px;padding:15px;
                                      font-family:monospace;font-size:13px;
                                      color:#333;white-space:pre-wrap;">{message}</div>
                        </td>
                      </tr>
                      <tr>
                        <td style="background:#232F3E;padding:15px 30px;text-align:center;">
                          <p style="color:#aaa;margin:0;font-size:12px;">
                            Amazon Product Recommendation System | samara-a2d79 | MLflow + Airflow + BigQuery
                          </p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </body>
            </html>
            """.format(now=now, subject=subject, message=message)

            msg.attach(MIMEText(message, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipients, msg.as_string())

            logger.info("Email enviado para {}: {}".format(self.recipients, subject))
            return True

        except Exception as e:
            logger.error("Falha no email: {}".format(e))
            return False


class AlertManager:
    def __init__(self):
        self.email = EmailAlert()

    def send_all(self, subject: str, message: str) -> dict:
        ok = self.email.send(subject, message)
        if not ok:
            logger.error("Alerta de email falhou.")
        return {"email": ok}

    def notify_retrain_complete(self, run_id: str, metrics: dict):
        subject = "[ML] Retreinamento Concluido"
        message = (
            "Retreinamento finalizado com sucesso!\n\n"
            "MLflow Run ID : {}\n"
            "Precision@5   : {}\n"
            "F1@5          : {}\n"
            "Hit Rate@5    : {}\n\n"
            "Novo modelo em producao."
        ).format(
            run_id,
            metrics.get("precision_at_5", "N/A"),
            metrics.get("f1_at_5", "N/A"),
            metrics.get("hit_rate_at_5", "N/A"),
        )
        return self.send_all(subject, message)

    def notify_retrain_failed(self, error: str):
        subject = "[ML] Retreinamento FALHOU"
        message = (
            "O retreinamento falhou!\n\n"
            "Erro:\n{}\n\n"
            "Verifique os logs do MLflow e do Airflow."
        ).format(error)
        return self.send_all(subject, message)

    def notify_degradation(self, metrics: dict, degradations: list):
        subject = "[ML] Degradacao de Modelo Detectada"
        lines = [
            "Degradacao detectada em {}\n".format(datetime.now().strftime("%d/%m/%Y %H:%M")),
            "Precision@5 atual : {}".format(metrics.get("precision_at_5", "N/A")),
            "Hit Rate@5 atual  : {}".format(metrics.get("hit_rate_at_5", "N/A")),
            "NDCG@5 atual      : {}".format(metrics.get("ndcg_at_5", "N/A")),
            "",
            "Quedas detectadas:",
        ]
        for d in degradations:
            lines.append("  - {}: queda de {}%".format(d["metric"], d["drop_pct"]))
        lines.append("\nAcao: retreinamento automatico acionado.")
        return self.send_all(subject, "\n".join(lines))

    def notify_api_error(self, endpoint: str, error: str):
        subject = "[ML] Erro na API"
        message = (
            "Erro detectado na API!\n\n"
            "Endpoint : {}\n"
            "Erro     : {}\n"
            "Horario  : {}"
        ).format(endpoint, error, datetime.now().strftime("%d/%m/%Y %H:%M"))
        return self.send_all(subject, message)

    def notify_data_quality(self, stats: dict, issues: list):
        status = "PROBLEMAS" if issues else "OK"
        subject = "[ML] {} - Qualidade dos Dados".format(status)
        lines = [
            "Relatorio diario - {}\n".format(datetime.now().strftime("%d/%m/%Y")),
            "Total reviews    : {:,}".format(stats.get("total_rows", 0)),
            "Produtos unicos  : {}".format(stats.get("unique_products", 0)),
            "Usuarios unicos  : {}".format(stats.get("unique_users", 0)),
            "Rating medio     : {:.2f}".format(stats.get("avg_rating", 0)),
        ]
        if issues:
            lines.append("\nProblemas:")
            for i in issues:
                lines.append("  - {}".format(i))
        return self.send_all(subject, "\n".join(lines))

    def notify_batch_prediction(self, knn_count: int, ncf_count: int):
        subject = "[ML] Previsoes em Lote Concluidas"
        message = (
            "Batch de previsoes finalizado!\n\n"
            "KNN recomendacoes : {:,}\n"
            "NCF recomendacoes : {:,}\n"
            "Salvo em          : amazon_reviews.knn_recommendations\n"
            "                    amazon_reviews.ncf_recommendations\n"
            "Horario           : {}"
        ).format(knn_count, ncf_count, datetime.now().strftime("%d/%m/%Y %H:%M"))
        return self.send_all(subject, message)
