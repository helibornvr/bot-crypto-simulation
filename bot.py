#!/usr/bin/env python3
"""Bot crypto en SIMULATION (argent fictif).

A chaque passage (toutes les 10 minutes environ) :
  1. lit les vrais prix publics de Coinbase en euros (aucune cle, aucun compte) ;
  2. applique les regles du Carnet de cycles crypto avec de l'argent fictif ;
  3. envoie une notification sur le telephone (application ntfy) quand une
     action est a faire : acheter, vendre, quelle crypto, quel montant, quel prix.

Le bot ne passe AUCUN ordre reel et ne se connecte a aucun compte.
Aucune bibliotheque a installer : Python 3.9+ suffit.
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ICI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ICI, "config.json")
ETAT = os.path.join(ICI, "etat.json")
JOURNAL = os.path.join(ICI, "journal.csv")
PARIS = ZoneInfo("Europe/Paris")
UA = {"User-Agent": "bot-simulation-crypto/1.0"}


# ---------------------------------------------------------------- outils
def lire_json(chemin, defaut=None):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defaut


def ecrire_json(chemin, data):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def euros(v):
    """Format francais : 1 234,56 EUR, avec plus de decimales pour les petits prix."""
    a = abs(v)
    d = 0 if a >= 1000 else 1 if a >= 100 else 2 if a >= 1 else 4 if a >= 0.1 else 5
    s = f"{v:,.{d}f}".replace(",", " ").replace(".", ",")
    return s + " €"


def montant(v):
    """Montant en euros, toujours 2 decimales."""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"


def pct(v):
    return f"{v:+.1f} %".replace(".", ",")


# ---------------------------------------------------------------- prix
def prix_coinbase(sym):
    """Prix 'spot' affiche par Coinbase, en euros."""
    d = get_json(f"https://api.coinbase.com/v2/prices/{sym}-EUR/spot")
    return float(d["data"]["amount"])


def variation_btc_24h():
    """Variation du BTC sur 24 h en %, d'apres Coinbase Exchange."""
    d = get_json("https://api.exchange.coinbase.com/products/BTC-EUR/stats")
    ouv, der = float(d["open"]), float(d["last"])
    return (der / ouv - 1) * 100


# ---------------------------------------------------------------- notifications
def notifier(titre, message, priorite=3, tags=""):
    """Envoie une notification via ntfy.sh. Sans sujet configure : affiche seulement."""
    print(f"\n[NOTIF] {titre}\n{message}\n")
    sujet = os.environ.get("NTFY_TOPIC", "").strip()
    if not sujet:
        return
    serveur = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    corps = {"topic": sujet, "title": titre, "message": message, "priority": priorite,
             "tags": [t for t in tags.split(",") if t]}
    req = urllib.request.Request(
        serveur + "/", data=json.dumps(corps).encode("utf-8"),
        headers={**UA, "Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # une notif ratee ne doit pas bloquer la simulation
        print(f"Notification non envoyee : {e}", file=sys.stderr)


# ---------------------------------------------------------------- etat
def etat_initial(cfg):
    return {
        "cycle": cfg["cycle"],
        "debut": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "liquidites": float(cfg["capital_depart_eur"]),
        "encaisse": 0.0,
        "pause_danger": False,
        "achats_bloques": False,
        "arret_total": False,
        "cycle_bouclable_signale": False,
        "dernier_bilan": "",
        "positions": {
            c["symbole"]: {
                "statut": "attente",  # attente, t1, t2, t12, tp1, clos
                "t1": False, "t2": False,
                "quantite": 0.0, "investi": 0.0, "recu": 0.0,
                "stop": c["stop"], "dernier_prix": None,
            }
            for c in cfg["cryptos"]
        },
    }


def journaliser(sym, action, prix, montant, quantite, raison):
    neuf = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if neuf:
            w.writerow(["date_paris", "crypto", "action", "prix_eur", "montant_eur", "quantite", "raison"])
        w.writerow([datetime.now(PARIS).strftime("%Y-%m-%d %H:%M"), sym, action,
                    f"{prix:.6g}", f"{montant:.2f}", f"{quantite:.8g}", raison])


# ---------------------------------------------------------------- simulation
def acheter(etat, cfg, c, p, tranche, prix):
    mise = c["budget_eur"] / 2
    frais = mise * cfg["frais_pct"] / 100
    qte = (mise - frais) / prix
    p["quantite"] += qte
    p["investi"] += mise
    p[tranche] = True
    p["statut"] = "t12" if p["t1"] and p["t2"] else tranche
    etat["liquidites"] -= mise
    journaliser(c["symbole"], f"achat {tranche}", prix, mise, qte, "prix sous le seuil d'achat")
    num = "1" if tranche == "t1" else "2"
    reste = ""
    if not (p["t1"] and p["t2"]):
        autre = c["t2"] if tranche == "t1" else c["t1"]
        reste = f"\nL'autre tranche reste en attente à {euros(autre)}."
    notifier(
        f"ACHETER {c['symbole']} · tranche {num}",
        f"Achète {montant(mise)} de {c['symbole']} au prix limite de {euros(c[tranche])} "
        f"(prix actuel {euros(prix)}).\n"
        f"Puis pose un stop à {euros(p['stop'])}.\n"
        f"Objectifs : {euros(c['tp1'])} (vendre la moitié), puis {euros(c['tp2'])}.{reste}",
        priorite=4, tags="moneybag",
    )


def vendre(etat, cfg, c, p, part, prix, raison):
    qte = p["quantite"] * part
    brut = qte * prix
    net = brut * (1 - cfg["frais_pct"] / 100)
    p["quantite"] -= qte
    p["recu"] += net
    etat["encaisse"] += net
    journaliser(c["symbole"], f"vente {int(part*100)} %", prix, net, qte, raison)
    return net


def traiter_crypto(etat, cfg, c, prix, achats_ok):
    sym = c["symbole"]
    p = etat["positions"][sym]
    p["dernier_prix"] = prix
    if p["statut"] == "clos":
        return

    en_position = p["quantite"] > 0

    # 1) Stop : priorite absolue
    if en_position and prix <= p["stop"]:
        net = vendre(etat, cfg, c, p, 1.0, prix, "stop touché")
        p["statut"] = "clos"
        res = p["recu"] - p["investi"]
        notifier(
            f"VENDRE {sym} · stop touché",
            f"Le prix ({euros(prix)}) est passé sous ton stop à {euros(p['stop'])}.\n"
            f"Vends tout ton {sym} (si ton ordre stop ne l'a pas déjà fait).\n"
            f"Résultat simulé sur {sym} : {montant(res)}. La position est close.",
            priorite=5, tags="rotating_light",
        )
        return

    # 2) Objectif 1 : vendre la moitie, remonter le stop au prix moyen
    if en_position and p["statut"] in ("t1", "t2", "t12") and prix >= c["tp1"]:
        prix_moyen = p["investi"] / (p["quantite"] / (1 - cfg["frais_pct"] / 100))
        vendre(etat, cfg, c, p, 0.5, prix, "objectif 1")
        p["stop"] = round(prix_moyen, 8)
        p["statut"] = "tp1"
        notifier(
            f"VENDRE 50 % de {sym} · objectif 1",
            f"{sym} est à {euros(prix)}, au-dessus de l'objectif 1 ({euros(c['tp1'])}).\n"
            f"Vends la moitié de ton {sym}.\n"
            f"Puis remonte ton stop à ton prix d'achat moyen, environ {euros(prix_moyen)}, "
            f"et annule la tranche d'achat encore en attente.\n"
            f"Le reste vise {euros(c['tp2'])}.",
            priorite=4, tags="chart_with_upwards_trend",
        )
        return

    # 3) Objectif 2 : vendre le reste
    if en_position and p["statut"] == "tp1" and prix >= c["tp2"]:
        vendre(etat, cfg, c, p, 1.0, prix, "objectif 2")
        p["statut"] = "clos"
        res = p["recu"] - p["investi"]
        notifier(
            f"VENDRE le reste de {sym} · objectif 2",
            f"{sym} est à {euros(prix)}, au-dessus de l'objectif 2 ({euros(c['tp2'])}).\n"
            f"Vends tout le {sym} qui te reste.\n"
            f"Résultat simulé sur {sym} : {montant(res)}. Position close.",
            priorite=4, tags="tada",
        )
        return

    # 4) Achats en deux tranches (jamais apres l'objectif 1, jamais sous le stop)
    if not achats_ok or p["statut"] == "tp1" or prix <= c["stop"]:
        return
    if not p["t1"] and prix <= c["t1"]:
        acheter(etat, cfg, c, p, "t1", prix)
    if not p["t2"] and prix <= c["t2"]:
        acheter(etat, cfg, c, p, "t2", prix)


def valeur_cycle(etat):
    pos = sum(p["quantite"] * (p["dernier_prix"] or 0) for p in etat["positions"].values())
    return etat["liquidites"] + pos + etat["encaisse"]


def tout_vendre(etat, cfg, prix):
    for c in cfg["cryptos"]:
        p = etat["positions"][c["symbole"]]
        if p["quantite"] > 0 and c["symbole"] in prix:
            vendre(etat, cfg, c, p, 1.0, prix[c["symbole"]], "arrêt total -20 %")
        if p["statut"] != "clos":
            p["statut"] = "clos"


def bilan(etat, cfg):
    cap = cfg["capital_depart_eur"]
    v = valeur_cycle(etat)
    lignes = [f"Valeur du cycle : {montant(v)} ({pct((v / cap - 1) * 100)} sur {montant(cap)})"]
    for c in cfg["cryptos"]:
        p = etat["positions"][c["symbole"]]
        if p["investi"] == 0:
            continue
        val = p["quantite"] * (p["dernier_prix"] or 0) + p["recu"]
        lignes.append(f"{c['symbole']} : {p['statut']}, {montant(val - p['investi'])}")
    attente = [c["symbole"] for c in cfg["cryptos"] if etat["positions"][c["symbole"]]["statut"] == "attente"]
    if attente:
        lignes.append("En attente d'achat : " + ", ".join(attente))
    if etat["pause_danger"]:
        lignes.append("Achats en pause (BTC en forte baisse sur 24 h).")
    if etat["achats_bloques"]:
        lignes.append("Achats bloqués (cycle sous -10 %).")
    return "\n".join(lignes)


def passage(cfg, etat, prix, var_btc):
    """Un passage complet du bot. Separe du reseau pour pouvoir etre teste."""
    if etat["arret_total"]:
        return

    # Garde-fou 1 : danger de marche (BTC en forte baisse sur 24 h)
    if var_btc is not None:
        danger = var_btc <= cfg["pause_si_btc_24h_pct"]
        if danger != etat["pause_danger"]:
            etat["pause_danger"] = danger
            if danger:
                notifier("PAUSE des achats", f"Le bitcoin a perdu {pct(abs(var_btc))[1:]} en 24 h.\n"
                         "N'achète rien de nouveau pour l'instant. Garde tes stops en place.\n"
                         "Annule les ordres d'achat limites encore ouverts si tu en as.",
                         priorite=4, tags="warning")
            else:
                notifier("Fin de la pause des achats", f"Le bitcoin est revenu à {pct(var_btc)} sur 24 h.\n"
                         "Les achats aux seuils du carnet sont de nouveau autorisés.", priorite=3,
                         tags="white_check_mark")

    # Positions : stops et objectifs d'abord, achats si autorises
    achats_ok = not etat["pause_danger"] and not etat["achats_bloques"]
    for c in cfg["cryptos"]:
        if c["symbole"] in prix:
            traiter_crypto(etat, cfg, c, prix[c["symbole"]], achats_ok)

    # Garde-fous 2 et 3 : valeur du cycle
    cap = cfg["capital_depart_eur"]
    v = valeur_cycle(etat)
    ecart = (v / cap - 1) * 100
    if ecart <= cfg["arret_total_pct"]:
        tout_vendre(etat, cfg, prix)
        etat["arret_total"] = True
        notifier("VENDRE TOUT · arrêt du cycle",
                 f"Le cycle vaut {montant(v)}, soit {pct(ecart)} sous les {montant(cap)} de départ.\n"
                 "Règle des -20 % : vends toutes tes positions et annule tous tes ordres.\n"
                 "Le bot s'arrête jusqu'au prochain cycle.", priorite=5, tags="sos")
        return
    bloque = ecart <= cfg["blocage_achats_pct"]
    if bloque != etat["achats_bloques"]:
        etat["achats_bloques"] = bloque
        if bloque:
            notifier("Achats BLOQUÉS · cycle à -10 %",
                     f"Le cycle vaut {montant(v)} ({pct(ecart)}).\nPlus aucun nouvel achat. "
                     "Annule tes ordres d'achat limites encore ouverts. Les stops restent en place.",
                     priorite=4, tags="no_entry")
        else:
            notifier("Achats de nouveau autorisés", f"Le cycle est remonté à {montant(v)} ({pct(ecart)}).",
                     priorite=3, tags="white_check_mark")

    # Fin de cycle : toutes les cryptos closes, ou duree maximale atteinte sans position ouverte
    pos = etat["positions"].values()
    ouvertes = [p for p in pos if p["statut"] not in ("attente", "clos")]
    closes = [p for p in pos if p["statut"] == "clos" and p["investi"] > 0]
    jours = (datetime.now(timezone.utc) - datetime.fromisoformat(etat["debut"])).days
    fini = all(p["statut"] == "clos" for p in pos) or jours >= cfg["duree_max_cycle_jours"]
    if fini and closes and not ouvertes and not etat["cycle_bouclable_signale"]:
        etat["cycle_bouclable_signale"] = True
        gain = sum(p["recu"] - p["investi"] for p in closes)
        txt = (f"Toutes tes positions achetées sont closes. Résultat simulé : {montant(gain)}.\n")
        txt += (f"Si tu veux boucler le cycle : convertis {montant(gain)} en BTC, puis demande à Claude "
                "des niveaux à jour pour le cycle suivant." if gain > 0 else
                "Pas de gain à convertir en BTC. Demande à Claude des niveaux à jour avant de relancer.")
        notifier("Cycle bouclable", txt, priorite=3, tags="checkered_flag")


def main():
    cfg = lire_json(CONFIG)
    etat = lire_json(ETAT)
    if etat is None or etat.get("cycle") != cfg["cycle"]:
        etat = etat_initial(cfg)
        notifier(f"Bot démarré · cycle {cfg['cycle']}",
                 f"Simulation avec {montant(cfg['capital_depart_eur'])} fictifs sur "
                 f"{len(cfg['cryptos'])} cryptos. Tu recevras une notification à chaque action à faire.",
                 priorite=3, tags="robot")

    prix, erreurs = {}, []
    for c in cfg["cryptos"]:
        try:
            prix[c["symbole"]] = prix_coinbase(c["symbole"])
        except Exception as e:
            erreurs.append(f"{c['symbole']} ({e})")
    try:
        var_btc = variation_btc_24h()
    except Exception as e:
        var_btc = None
        erreurs.append(f"variation BTC 24 h ({e})")
    if erreurs:
        print("Prix indisponibles : " + ", ".join(erreurs), file=sys.stderr)

    print(datetime.now(PARIS).strftime("%d/%m %H:%M"), {k: euros(v) for k, v in prix.items()},
          f"BTC 24 h : {pct(var_btc) if var_btc is not None else '?'}")
    passage(cfg, etat, prix, var_btc)

    # Bilan quotidien : prouve aussi que le bot tourne toujours
    maintenant = datetime.now(PARIS)
    jour = maintenant.strftime("%Y-%m-%d")
    if maintenant.hour >= cfg["heure_bilan_paris"] and etat["dernier_bilan"] != jour:
        etat["dernier_bilan"] = jour
        txt = bilan(etat, cfg)
        if erreurs:
            txt += "\nPrix indisponibles au dernier passage : " + ", ".join(e.split(" ")[0] for e in erreurs)
        notifier("Bilan du jour (simulation)", txt, priorite=2, tags="bar_chart")

    ecrire_json(ETAT, etat)


if __name__ == "__main__":
    main()
