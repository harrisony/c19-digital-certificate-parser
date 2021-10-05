import pdfplumber
import pyodbc
import io

# https://www.servicesaustralia.gov.au/organisations/health-professionals/services/medicare/medicare-online-software-developers/resources/formats-exchange-electronic-data/air-vaccine-code-formats
VACCINES = {'Pfizer Comirnaty' : 'COMIRN',
            'AstraZeneca Vaxzevria': 'COVAST',
            'COVID-19 Vaccine AstraZeneca': 'COVAST',
            # TODO: Haven't encontered these
            'Moderna Spikevax': 'MODERN',
            'Janssen-Cilag COVID Vaccine': 'JANSSE'}


def parse_cis(pp):
    contents = pp.pages[0].extract_text().split('\n')
    name = contents[3]
    name = ' '.join(name.split(' ')[:-3])

    # If you have a long name, thanks to Ev for giving me me his docs
    if contents[5] == 'Individual Healthcare Identifier (IHI) Document number':
        name = name + contents[4]
        contents.pop(4)

    vax = contents[9]
    dates = ' '.join(vax.split(' ')[-6:]).split(',')
    vax = ' '.join(vax.split(' ')[:-6])

    # this occurs if you have an earlier CIS where it was known as 'COVID-19 Vaccine AstraZeneca'
    # just give them the new name and be donewith it
    if contents[10] == 'AstraZeneca':
        vax = 'AstraZeneca Vaxzevria'

    elif contents[10] != 'Disclaimer':
        print("ERRRORRR")
        for i, item in enumerate(contents):
            print(i, item)
    code = VACCINES.get(vax)
    vrecord = {'name': name, 'vax': [(vax, code, i.strip()) for i in dates]}
    return vrecord


def parse_ihs(pp):
    vax = []
    contents = pp.pages[0].extract_text().split('\n')
    if contents[1] == 'Immunisation history statement':
        contents.pop(0)
    # Skip For:
    name = contents[2][5:]
    for page in pp.pages:
        if page.find_tables():
            for e in page.extract_table():
                if e[1] == 'COVID-19':
                    name = e[2].replace('\n', '')
                    code = VACCINES.get(name)
                    vax.append((name, code, e[0]))

    vrecord = {'name': name, 'vax': vax}
    if len(vax):
        return vrecord
    else:
        return {}


def parse_pdf(f):
    try:
        pp = pdfplumber.open(f)
    except TypeError:  # sometimes, it just dies
        return {}
    contents = pp.pages[0].extract_text()
    if contents:
        contents = contents.split('\n')
        if len(contents) == 1: return {}
    else:
        return {}
    if contents[0] == 'COVID-19 digital certificate':
        return parse_cis(pp)
    elif contents[0] == 'Immunisation history statement' or contents[1] == 'Immunisation history statement':
        return parse_ihs(pp)
    else:
        return {}


if __name__ == '__main__':
    jabba = []  # jabba the hutt

    jabba.append(parse_pdf('examples/IHSHC.pdf'))
    jabba.append(parse_pdf('examples/IHS-ev.pdf'))
    jabba.append(parse_pdf('examples/digitalcert-ev.pdf'))

    import json
    json.dump(jabba, open('vax.json', 'w'))

