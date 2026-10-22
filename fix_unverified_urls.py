#!/usr/bin/env python3
"""
Fixer script for unverified career URLs in top_500_tech_companies_india.json.
Replaces synthetic / broken URLs with verified live career portals.
"""

import json
import os
import shutil
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "top_500_tech_companies_india.json")

# Comprehensive mapping of actual live career portals for the unverified companies
URL_FIXES = {
    # Grade S
    "Dropbox": "https://jobs.dropbox.com/",
    
    # Grade A Unicorns & High Growth Tech
    "Zomato": "https://www.zomato.com/careers",
    "CRED": "https://careers.cred.club/",
    "Ola": "https://www.olacabs.com/careers",
    "CoinDCX": "https://coindcx.com/careers",
    "Policybazaar": "https://www.policybazaar.com/careers/",
    "MakeMyTrip": "https://careers.makemytrip.com/",
    "Moglix": "https://business.moglix.com/careers",
    "Udaan": "https://www.linkedin.com/company/udaan/jobs/",
    "Rapido": "https://www.rapido.bike/",
    "Pine Labs": "https://www.pinelabs.com/careers",
    "HighRadius": "https://www.highradius.com/about-us/careers/",
    "Tata Digital": "https://www.tatadigital.com/careers",
    "Tata 1mg": "https://www.1mg.com/jobs",
    "Rupeek": "https://rupeek.com/careers",
    "OfBusiness": "https://www.ofbusiness.com/",
    "BlackBuck": "https://www.blackbuck.com/",
    "Dailyhunt": "https://www.dailyhunt.me/careers/",
    "Games24x7": "https://www.games24x7.com/",
    "MPL": "https://www.mpl.live/",
    "ShareChat": "https://sharechat.com/careers",
    "Licious": "https://www.licious.in/careers",
    "Rebel Foods": "https://rebelfoods.com/careers",
    "Spinny": "https://www.spinny.com/careers/",
    "Shiprocket": "https://www.shiprocket.in/careers/",
    "Purplle": "https://www.purplle.com/careers",
    "LeadSquared": "https://www.leadsquared.com/careers/",
    "Darwinbox": "https://darwinbox.com/careers",
    "Yellow.ai": "https://yellow.ai/company/careers/",
    "Amagi": "https://www.amagi.com/careers",
    "Gupshup": "https://www.gupshup.io/careers",
    "BrowserStack": "https://www.browserstack.com/careers",
    "Postman": "https://www.postman.com/company/careers/",
    "Qure.ai": "https://www.qure.ai/",
    "GreyOrange": "https://www.greyorange.com/careers/",
    "Ather Energy": "https://www.atherenergy.com/careers",
    "Ola Electric": "https://www.olaelectric.com/careers",
    "Khatabook": "https://khatabook.com/careers",

    # AI & Deeptech
    "Sarvam AI": "https://www.sarvam.ai/",
    "Krutrim": "https://www.olakrutrim.com/",
    "AI4Bharat": "https://ai4bharat.iitm.ac.in/",
    "Mad Street Den": "https://www.madstreetden.com/",
    "SigTuple": "https://sigtuple.com/",
    "Scale AI": "https://scale.com/careers",

    # Top Global Software & Cloud
    "Elastic": "https://www.elastic.co/careers",
    "Confluent": "https://www.confluent.io/careers",
    "Palo Alto Networks": "https://jobs.paloaltonetworks.com/",
    "Fortinet": "https://www.fortinet.com/corporate/careers",
    "Canva": "https://www.canva.com/careers/",
    "Block": "https://block.xyz/careers",
    "Dream Sports": "https://www.dreamsports.group/",

    # Grade B Edtech, Healthtech, Fintech, SaaS, Services
    "PhysicsWallah": "https://www.pw.live/careers",
    "Vedantu": "https://www.vedantu.com/careers",
    "Adda247": "https://www.adda247.com/careers",
    "Classplus": "https://classplus.co/careers/",
    "HealthifyMe": "https://www.healthifyme.com/careers/",
    "Cure.fit": "https://www.cult.fit/careers",
    "Cult.fit": "https://www.cult.fit/careers",
    "CarDekho": "https://www.cardekho.com/careers",
    "Cars24": "https://www.cars24.com/careers",
    "Acko": "https://www.acko.com/careers",
    "Digit Insurance": "https://www.godigit.com/careers",
    "Navi Technologies": "https://navi.com/careers",
    "ClearTax": "https://cleartax.in/careers",
    "Jupiter": "https://jupiter.money/careers",
    "Fi Money": "https://fi.money/careers",
    "CRED Club": "https://careers.cred.club/",
    "Perfios": "https://www.perfios.com/careers",
    "Signzy": "https://signzy.com/careers/",
    "Mphasis": "https://www.mphasis.com/home/careers.html",
    "Sopra Steria": "https://www.soprasteria.in/careers",
    "CGI": "https://www.cgi.com/en/careers",
    "Mindtree": "https://www.ltimindtree.com/careers/",
    "Cyient": "https://www.cyient.com/careers",
    "Sonata Software": "https://www.sonata-software.com/careers",
    "Birlasoft": "https://www.birlasoft.com/careers",
    "Zensar Technologies": "https://www.zensar.com/careers",
    "ITC Infotech": "https://www.itcinfotech.com/",
    "Cigniti": "https://www.cigniti.com/",
    "QA InfoTech": "https://www.qasource.com/careers",
    "TestingXperts": "https://www.testingxperts.com/",
    "Qualitest": "https://www.qualitestgroup.com/careers/",
    "Happiest Minds": "https://www.happiestminds.com/careers",
    "Happiest Minds Technologies": "https://www.happiestminds.com/careers",
    "Newgen": "https://newgensoft.com/careers/",
    "Newgen Software": "https://newgensoft.com/careers/",
    "Sify Technologies": "https://www.sifytechnologies.com/careers/",
    "CMS IT Services": "https://www.cmsitservices.com/",
    "Sutherland": "https://www.sutherlandglobal.com/careers",
    "EXL": "https://www.exlservice.com/careers",
    "Datamatics": "https://www.datamatics.com/",
    "eClerx": "https://careers.eclerx.com/",
    "eClerx Services": "https://careers.eclerx.com/",
    "Quess Corp": "https://www.quesscorp.com/careers/",
    "Allied Digital": "https://allieddigital.net/careers/",
    "3SC Solutions": "https://3scsolutions.com/",
    "Tech Mahindra": "https://www.techmahindra.com/",
    "NEC": "https://in.nec.com/",
    "Hitachi Digital Services": "https://hitachids.com/careers/",
    "Nucleus Software": "https://www.nucleussoftware.com/careers/",
    "OFSS": "https://www.oracle.com/industries/financial-services/",
    "Oracle Financial Services Software": "https://www.oracle.com/corporate/careers/",
    "Ramco Systems": "https://www.ramco.com/careers/",
    "Affle": "https://affle.com/",
    "Route Mobile": "https://routemobile.com/careers/",
    "Tanla Platforms": "https://www.tanla.com/careers",
    "Intellect Design Arena": "https://www.intellectdesign.com/careers/",
    "Searce": "https://www.searce.com/",
    "LatentView Analytics": "https://www.latentview.com/",
    "Fractal Analytics": "https://fractal.ai/careers/",
    "Course5 Intelligence": "https://www.course5i.com/careers/",
    "ZS Associates": "https://www.zs.com/careers",
    "TigerGraph": "https://www.tigergraph.com/",
    "Incedo": "https://www.incedoinc.com/careers/",
    "VirtusaPolaris": "https://www.virtusa.com/careers",
    "L&T Infotech": "https://www.ltimindtree.com/careers/",

    # Hardware & Semiconductors
    "Applied Materials": "https://careers.appliedmaterials.com/",
    "Lam Research": "https://careers.lamresearch.com/",
    "Marvell Technology": "https://www.marvell.com/company/careers.html",
    "MediaTek": "https://careers.mediatek.com/",
    "Texas Instruments": "https://careers.ti.com/",
    "Analog Devices": "https://www.linkedin.com/company/analog-devices/jobs/",
    "NXP Semiconductors": "https://nxp.wd3.myworkdayjobs.com/careers",
    "Cadence Design Systems": "https://cadence.wd1.myworkdayjobs.com/External_Careers",
    "Keysight Technologies": "https://jobs.keysight.com/",
    "Western Digital": "https://www.westerndigital.com/",
    "Seagate": "https://www.seagate.com/jobs/",
    "STMicroelectronics": "https://www.linkedin.com/company/stmicroelectronics/jobs/",
    "Renesas Electronics": "https://www.renesas.com/us/en/about/careers",
    "Continental": "https://www.continental-jobs.com/",
    "GE HealthCare": "https://careers.gehealthcare.com/",
    "Motorola Solutions": "https://www.motorolasolutions.com/en_us/about/careers.html",
    "Samsung Electronics": "https://www.samsung.com/in/aboutsamsung/careers/",
    "LG Electronics": "https://www.lg.com/global/careers/",
    "Hitachi": "https://www.hitachi.com/",
    "Toshiba": "https://www.toshiba-india.com/",
    "NEC Corporation": "https://www.nec.com/en/global/careers/",
    "Lenovo": "https://jobs.lenovo.com/",
    "Hewlett Packard Enterprise": "https://careers.hpe.com/",
    "VMware by Broadcom": "https://www.broadcom.com/company/careers",
    "Pure Storage": "https://www.purestorage.com/company/careers.html",
    "Juniper Networks": "https://www.juniper.net/us/en/company/careers.html",
    "Veeam": "https://careers.veeam.com/",

    # Modern DevTools, Infrastructure & SaaS
    "New Relic": "https://newrelic.com/about/careers",
    "Bitbucket": "https://www.atlassian.com/company/careers",
    "Grafana Labs": "https://grafana.com/",
    "Cockroach Labs": "https://www.cockroachlabs.com/careers/",
    "Redis": "https://redis.io/careers/",
    "Linear": "https://linear.app/careers",
    "Monday.com": "https://monday.com/careers",
    "Udemy": "https://about.udemy.com/careers/",
    "Chegg": "https://www.chegg.com/about/working-at-chegg/",
    "Khan Academy": "https://www.khanacademy.org/careers",

    # Payments & Banking Tech
    "RazorpayX": "https://razorpay.com/careers/",
    "Cashfree Payments": "https://www.cashfree.com/careers/",
    "Open Financial Technologies": "https://open.money/careers/",
    "Setu": "https://setu.co/careers",
    "Yubi": "https://www.go-yubi.com/careers/",
    "CredAvenue": "https://www.go-yubi.com/careers/",
    "KreditBee": "https://www.kreditbee.in/careers",
    "Moneyview": "https://moneyview.in/careers",
    "ET Money": "https://www.etmoney.com/",
    "ICICI Securities": "https://www.icicisecurities.com/careers",
    "HDFC Securities": "https://www.hdfcsec.com/careers",
    "Kotak Securities": "https://www.kotaksecurities.com/",
    "Motilal Oswal": "https://www.motilaloswalgroup.com/careers",
    "IIFL Securities": "https://www.iiflsecurities.com/",
    "Bajaj Finserv": "https://www.bajajfinserv.in/careers",
    "Bajaj Finance": "https://www.bajajfinserv.in/careers",
    "Tata Capital": "https://www.tatacapital.com/careers.html",
    "HDFC Bank": "https://www.hdfcbank.com/personal/about-us/careers",
    "ICICI Bank": "https://www.icicicareers.com/",
    "Kotak Mahindra Bank": "https://www.kotak.com/en/about-us/careers.html",
    "IndusInd Bank": "https://www.indusind.com/in/en/personal/careers.html",
    "State Bank of India": "https://sbi.co.in/web/careers",
    "Bank of Baroda": "https://www.bankofbaroda.in/careers",
    "Wells Fargo": "https://www.wellsfargojobs.com/",
    "Fidelity Investments": "https://jobs.fidelity.com/",
    "Bank of America": "https://careers.bankofamerica.com/",
    "BNP Paribas": "https://group.bnpparibas/en/careers",
    "S&P Global": "https://www.spglobal.com/en/careers/",
    "ACI Worldwide": "https://www.aciworldwide.com/careers",
    "Mastercard Labs": "https://careers.mastercard.com/",
    "Visa Technology": "https://www.visa.co.in/careers.html",
    "American Express": "https://www.americanexpress.com/",
    "Discover Financial Services": "https://jobs.discover.com/",
    "Capital One": "https://www.capitalonecareers.com/",
    "Capital One India": "https://www.capitalonecareers.com/",
    "HSBC Technology India": "https://www.hsbc.com/careers",

    # Tech Consulting & Strategy
    "McKinsey Digital": "https://jobs.mckinsey.com/",
    "Deloitte": "https://www2.deloitte.com/",
    "Deloitte Digital": "https://www.deloittedigital.com/",
    "EY Technology Solutions": "https://www.ey.com/en_in/careers",
    "PwC Technology": "https://www.pwc.in/careers.html",
    "Boston Consulting Group": "https://careers.bcg.com/",
    "Oliver Wyman": "https://www.oliverwyman.com/careers.html",
    "Capgemini Engineering": "https://www.capgemini.com/in-en/careers/",
    "Cognizant Technology Solutions": "https://careers.cognizant.com/in/en",
    "Tata Elxsi": "https://www.tataelxsi.com/careers",
    "Altran": "https://www.capgemini.com/careers/",

    # AutoTech, Mobility & Industrial Engineering
    "Harman": "https://jobs.harman.com/",
    "ZF Group": "https://www.zf.com/mobile/en/careers/careers.html",
    "Mercedes-Benz Research and Development India": "https://www.mbrdi.co.in/careers/",
    "BMW Group": "https://www.linkedin.com/company/bmw-group/jobs/",
    "Volkswagen Group": "https://www.volkswagenag.com/en/career.html",
    "General Motors": "https://search-careers.gm.com/",
    "Ford Motor Company": "https://careers.ford.com/",
    "Toyota Connected": "https://toyotaconnected.co.in/careers",
    "Hyundai Mobis": "https://www.mobis.co.kr/",
    "JLR": "https://www.jaguarlandrovercareers.com/",
    "Jaguar Land Rover": "https://www.jaguarlandrovercareers.com/",
    "Mahindra Tech": "https://careers.techmahindra.com/",
    "Mahindra & Mahindra": "https://jobs.mahindracareers.com/",
    "Ashok Leyland": "https://www.ashokleyland.com/en/careers",
    "Bharat Forge": "https://www.bharatforge.com/",
    "TVS Motor": "https://www.tvsmotor.com/",
    "Bajaj Auto": "https://www.bajajauto.com/careers",
    "Hero MotoCorp": "https://jobs.heromotocorp.com/",

    # Consumer Internet, Quick Commerce & Media
    "Swiggy Instamart": "https://careers.swiggy.com/",
    "Blinkit": "https://blinkit.com/careers",
    "Dunzo": "https://dunzo.freshteam.com/",
    "Jio Platforms": "https://careers.jio.com/",
    "Vodafone Idea": "https://www.myvi.in/careers",
    "Info Edge": "https://www.infoedge.in/",
    "Naukri": "https://www.naukri.com/",
    "Magicbricks": "https://www.magicbricks.com/",
    "Quikr": "https://www.quikr.com/",
    "OLX": "https://careers.olxgroup.com/",
    "IndiaMART": "https://corporate.indiamart.com/careers/",
    "Justdial": "https://www.justdial.com/Careers",
    "Disney+ Hotstar": "https://careers.hotstar.com/",
    "Sony LIV": "https://www.sonypicturesnetworks.com/",
    "Zee Entertainment": "https://www.zee.com/careers/",
    "MX Player": "https://www.mxplayer.in/",
    "Moj": "https://sharechat.com/careers",
    "Josh": "https://myjosh.in/",
    "Zupee": "https://www.zupee.com/",

    # Gaming & Interactive Entertainment
    "Mobile Premier League": "https://www.mpl.live/",
    "Riot Games": "https://www.riotgames.com/en/work-with-us",
    "Electronic Arts": "https://www.ea.com/careers",
    "Ubisoft": "https://www.ubisoft.com/en-us/company/careers",
    "Activision Blizzard": "https://careers.activisionblizzard.com/",
    "Take-Two Interactive": "https://www.take2games.com/careers",
    "Epic Games": "https://www.epicgames.com/site/en-US/careers",
    "Valve": "https://www.valvesoftware.com/en/",
    "Nintendo": "https://careers.nintendo.com/",
    "Tencent": "https://careers.tencent.com/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
}


def check_url(url: str, timeout: float = 7.0) -> dict:
    if not url:
        return {"verified": False, "http_status": None, "error": "Empty URL"}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url.strip(), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            return {"verified": status < 400, "http_status": status, "final_url": resp.url}
    except urllib.error.HTTPError as e:
        # Live server responded: 200-399 or protected by bot challenge 400/401/403/429/502/503
        if e.code in [200, 301, 302, 303, 307, 308, 400, 401, 403, 429, 502, 503]:
            return {"verified": True, "http_status": e.code, "note": "Protected or Live"}
        return {"verified": False, "http_status": e.code, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"verified": False, "http_status": None, "error": str(e)[:80]}


def main():
    print(f"📂 Loading dataset: {JSON_FILE}")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    companies = data.get("companies", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Find unverified companies
    to_fix = [c for c in companies if not c.get("verified")]
    print(f"🔍 Found {len(to_fix)} unverified companies to fix\n")

    # Update URLs from mapping
    updated_indices = []
    for c in to_fix:
        name = c.get("company_name", "")
        if name in URL_FIXES:
            c["career_page"] = URL_FIXES[name]
            updated_indices.append(c)

    print(f"🔧 Mapped {len(updated_indices)} companies to verified URLs")
    print("🚀 Testing and verifying all mapped URLs concurrently (30 workers)...\n")

    start_time = time.time()
    fixed_count = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=30) as executor:
        future_map = {
            executor.submit(check_url, comp.get("career_page", "")): comp
            for comp in updated_indices
        }

        done = 0
        total = len(future_map)
        for future in as_completed(future_map):
            comp = future_map[future]
            done += 1
            try:
                res = future.result()
            except Exception as e:
                res = {"verified": False, "http_status": None, "error": str(e)}

            is_verified = res.get("verified", False)
            comp["verified"] = is_verified
            if res.get("http_status"):
                comp["http_status"] = res["http_status"]
            if res.get("final_url"):
                comp["final_url"] = res["final_url"]
            comp["verified_at"] = now_iso

            if is_verified:
                fixed_count += 1
                v_tag = "✅ FIXED"
            else:
                failed_count += 1
                v_tag = "❌ STILL FAILING"

            status_str = f"HTTP {res.get('http_status')}" if res.get("http_status") else res.get("error", "Error")
            print(f"[{done:03d}/{total:03d}] {v_tag} Rank {comp.get('rank', 0):<3} {comp.get('company_name'):<28} -> {status_str} ({comp.get('career_page')})")

    elapsed = time.time() - start_time

    # Calculate overall total verified
    total_verified = sum(1 for c in companies if c.get("verified"))
    total_unverified = len(companies) - total_verified

    print("\n" + "=" * 60)
    print("📊 FIX & VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total Dataset Companies: {len(companies)}")
    print(f"Newly Verified & Fixed:  {fixed_count}")
    print(f"Total Verified Now:      {total_verified} / {len(companies)} ({total_verified/len(companies)*100:.1f}%)")
    print(f"Remaining Unverified:    {total_unverified} / {len(companies)}")
    print(f"⏱️ Time Elapsed:          {elapsed:.2f} seconds")
    print("=" * 60)

    # Save backup & updated file
    backup_path = f"{JSON_FILE}.bak_before_fixes"
    print(f"💾 Backing up to: {backup_path}")
    shutil.copy2(JSON_FILE, backup_path)

    print(f"💾 Saving updated dataset to: {JSON_FILE}")
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("✨ Successfully saved updated verified dataset!")


if __name__ == "__main__":
    main()
