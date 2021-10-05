import pdfplumber
import io
import glob
import json

# https://www.servicesaustralia.gov.au/organisations/health-professionals/services/medicare/medicare-online-software-developers/resources/formats-exchange-electronic-data/air-vaccine-code-formats
VACCINES = {'Pfizer Comirnaty': 'COMIRN',
            'AstraZeneca Vaxzevria': 'COVAST',
            'COVID-19 Vaccine AstraZeneca': 'COVAST',
            # TODO: Haven't encountered these
            'Moderna Spikevax': 'MODERN',
            'Janssen-Cilag COVID Vaccine': 'JANSSE'}

FULLY_VACCINATED_YES = {'This individual has received all required COVID-19 vaccines.',  # digital certificate
                        'This individual has received all required COVID-19 vaccinations.'}  # IHS
FULLY_VACCINATED_NO = {'This individual has not received all required COVID-19 vaccines.'}  # IHS


def fully_vaccinated(line):
    if line in FULLY_VACCINATED_YES:
        return True
    if line in FULLY_VACCINATED_NO:
        return False
    return None


def parse_cis(pp):
    contents = pp.pages[0].extract_text().split('\n')
    person_name = contents[3]  # contents[3]: JABBA T HUTT 01 Jan 1990
    person_name = ' '.join(person_name.split(' ')[:-3])  # Strips off the date

    # If you have a long name, thanks to Ev for giving me me his docs
    if contents[5] == 'Individual Healthcare Identifier (IHI) Document number':
        person_name = person_name + contents[4]
        contents.pop(4)

    # contents[9]: 'AstraZeneca Vaxzevria 27 Aug 2021, 07 Oct 2021'
    # contents[9]: 'COVID-19 Vaccine  01 Apr 2021, 01 Jul 2021'
    vax_name = contents[9]
    dates = ' '.join(vax_name.split(' ')[-6:]).split(',')  # dates: ['01 Apr 2021', ' 01 Jul 2021']
    vax_name = ' '.join(vax_name.split(' ')[:-6])

    # this occurs if you have an earlier CIS where it was known as 'COVID-19 Vaccine AstraZeneca'
    # just give them the new name and be donewith it
    if contents[10] == 'AstraZeneca':
        vax_name = 'AstraZeneca Vaxzevria'

    elif contents[10] != 'Disclaimer':
        print("WARNING: Disclaimer not in line 10")

    all_doses = fully_vaccinated(contents[1])

    vax_code = VACCINES.get(vax_name)
    vrecord = {'name': person_name, 'vax': [(vax_name, vax_code, i.strip()) for i in dates],
               'required_vaccinations': all_doses}
    return vrecord


def parse_ihs(pp):
    vax = []
    contents = pp.pages[0].extract_text().split('\n')
    # Depending on export date, contents[0] is just 'australian government, services australia'
    if contents[1] == 'Immunisation history statement':
        contents.pop(0)

    # contents[2]: 'For: JABBA T HUTT'
    person_name = contents[2][5:]
    for page in pp.pages:
        if page.find_tables():
            for e in page.extract_table():
                if e[1] == 'COVID-19':
                    vax_date = e[0]
                    vax_name = e[2].replace('\n', '')  # Prevent "AstraZeneca\nVaxzevria"
                    vax_code = VACCINES.get(vax_name)
                    vax.append((vax_name, vax_code, vax_date))

    all_doses = fully_vaccinated(contents[7])

    vrecord = {'name': person_name, 'vax': vax, 'required_vaccinations': all_doses}
    if len(vax):
        return vrecord
    else:
        print("WARNING: No COVID-19 Vaccines given?")
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


def debug_page(f):
    print("FILE", f)
    pp = pdfplumber.open(f)
    for i, item in enumerate(pp.pages):
        print("PAGE", i)
        for j, line in enumerate(item.extract_text().split('\n')):
            print(j, line)


if __name__ == '__main__':
    jabba = []  # jabba the array ---  http://www.gvhealth.org.au/covid-19/vaxbus/
    pdfs = glob.glob("*.pdf")
    for pdf in pdfs:
        jabba.append(parse_pdf(pdf))
    json.dump(jabba, open('vax.json', 'w'))
