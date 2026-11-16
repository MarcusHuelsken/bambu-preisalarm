    results = {}
    for url in sorted(urls):
        try:
            page, _ = fetch(url)
            parser = JsonLdParser()
            parser.feed(page)
            for raw in parser.scripts:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                for node in jsonld_nodes(obj):
                    types = node.get("@type", [])
                    if isinstance(types, str):
                        types = [types]
                    if not any(t in ("Product", "ProductGroup") for t in types):
                        continue
                    title = str(node.get("name") or url.split("/")[-1])
                    if not PRINTER.search(title) or EXCLUDE.search(title):
                        continue
                    offers = node.get("offers", [])
                    if isinstance(offers, dict):
                        offers = [offers]
                    for i, offer in enumerate(offers):
                        if not isinstance(offer, dict):
                            continue
                        if str(offer.get("priceCurrency", "")).upper() != "EUR":
                            continue
                        cents = price_eur(offer.get("price"))
                        if not cents:
                            continue
                        name = title
                        key = f"{url}#{i}"
                        results[key] = {"name": name, "cents": cents, "url": url,
                                        "available": "instock" in str(offer.get("availability", "")).lower(),
                                        "source": "Produktseite (JSON-LD)"}
            time.sleep(0.15)
        except (OSError, ValueError) as exc:
            failures.append(f"{url}: {type(exc).__name__} {str(exc)[:90]}")
    return results, failures


def money(cents):
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def send_mail(report):
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("E-Mail nicht eingerichtet; es fehlen:", ", ".join(missing))
        return
    port = int(os.environ.get("SMTP_PORT") or "465")
    msg = EmailMessage()
    msg["Subject"] = "Bambu Lab Preischeck – " + dt.date.today().isoformat()
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content("Der aktuelle Preisbericht ist als HTML-Version dieser E-Mail enthalten.")
    msg.add_alternative(report, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        raise ValueError("SMTP_PORT muss 465 oder 587 sein")
    print("E-Mail erfolgreich verschickt")


def main():
    OUT.mkdir(exist_ok=True)
    products, errors = shopify_products()
    results = parse_shopify(products)
    if not results:
        print("Keine Drucker im Katalog gefunden; versuche Produktseiten mit JSON-LD.")
        results, fall_errors = html_fallback()
        errors.extend(fall_errors)
    old = {}
    try:
        old = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    entries = []
    for key, item in sorted(results.items(), key=lambda pair: (pair[1]["cents"], pair[1]["name"])):
        previous = old.get(key)
        change = item["cents"] - previous if isinstance(previous, int) else None
        entries.append({"id": key, **item, "previous_cents": previous, "change_cents": change})
    content = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "items": entries, "errors": errors}
    (OUT / "preise.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    trs = []
    for row in entries:
        delta = row["change_cents"]
        status = "neu/kein Vergleich" if delta is None else "unverändert" if delta == 0 else (("gesunken " if delta < 0 else "gestiegen ") + money(abs(delta)))
        availability = "Ja" if row["available"] is True else "Nein" if row["available"] is False else "Unbekannt"
        values = [row["name"], money(row["cents"]), status, availability, row["source"]]
        trs.append("<tr>" + "".join("<td>" + html.escape(v) + "</td>" for v in values) +
                   '<td><a href="' + html.escape(row["url"], quote=True) + '">Zum Shop</a></td></tr>')
    report = ("<h2>Bambu Lab – täglicher Preischeck</h2><p>" +
              html.escape(dt.date.today().isoformat()) + " · Offizieller EU-Shop · " + str(len(entries)) +
              " Varianten</p><p>Shoppreise ohne Gewähr; Versandkosten und externe Händler sind nicht enthalten. " +
              "Veränderungen nur bei vorhandenem Preisstand.</p>" +
              '<table border="1" cellpadding="5"><tr><th>Modell</th><th>Preis</th><th>Veränderung</th>' +
              '<th>Lieferbar</th><th>Datenquelle</th><th>Link</th></tr>' + "".join(trs) + "</table>")
    if errors:
        report += "<h3>Technische Hinweise</h3><p>" + html.escape("; ".join(errors[:15])) + "</p>"
    if not entries:
        report += "<p><strong>ACHTUNG: Keine verlässlichen EUR-Preise abrufbar.</strong></p>"
    (OUT / "bericht.html").write_text("<!doctype html><html lang='de'><meta charset='utf-8'><body>" + report + "</body></html>", encoding="utf-8")
    if not entries:
        print("FEHLER: Keine verifizierbaren EUR-Preise. Einzelheiten in output/preise.json")
        sys.exit(1)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({key: item["cents"] for key, item in results.items()}, indent=2), encoding="utf-8")
    print(f"Erfolg: {len(entries)} Produktvarianten mit EUR-Preis")
    send_mail(report)


if __name__ == "__main__":
    main()
