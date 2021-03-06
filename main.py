import glob
import io
import itertools
import json
import re

import pdfplumber
import rapidfuzz
from pdfminer.pdfparser import PDFSyntaxError
from pyzbar import pyzbar

try:
    from PIL import Image
except ImportError:
    import Image

import pytesseract
import fitz  # pymupdf

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract'

# https://www.servicesaustralia.gov.au/organisations/health-professionals/services/medicare/medicare-online-software-developers/resources/formats-exchange-electronic-data/air-vaccine-code-formats
VACCINES = {'Pfizer Comirnaty': 'COMIRN',
            'AstraZeneca Vaxzevria': 'COVAST',
            'COVID-19 Vaccine AstraZeneca': 'COVAST',
            'Moderna Spikevax': 'MODERN',
            # TODO: Haven't encountered these
            'Janssen-Cilag COVID Vaccine': 'JANSSE'}

FULLY_VACCINATED_YES = {'This individual has received all required COVID-19 vaccines.',  # digital certificate
                        'This individual has received all required COVID-19 vaccinations.'}  # IHS and c19 statement v2021.07.10
FULLY_VACCINATED_NO = {'This individual has not received all required COVID-19 vaccines.'}  # IHS

COVID_ALL = re.compile(
    r'This individual has (?P<negative>not )?received all required\sCOVID-19 (vaccines|vaccinations).')
COVID_DIGITAL_CERTIFICATE = re.compile(
    r'Vaccinations Dates received(\n*)(.*?) (\d{2} [a-zA-Z]{3} \d{4}), (\d{2} [a-zA-Z]{3} \d{4})')

COVID_IOS = re.compile(r'(.*?)\s+(\d{2} [a-zA-Z]{3} \d{4}), (\d{2} [a-zA-Z]{3} \d{4})')
IHS_STATEMENT = re.compile(r'(\d{2} [a-zA-Z]{3} \d{4}) COVID-19 (.*)')

# Captures:
# AstraZeneca Vaxzevria 27 Aug 2021, 07 Oct 2021
# AstraZeneca Vaxzevria 20 Aug 2021
DIGITAL_CERTIFICATE_VACCINE = re.compile(r'([a-zA-Z ]+) (\d{2} [a-zA-Z]{3} \d{4})(?:, (\d{2} [a-zA-Z]{3} \d{4}))?')

VDS_CODES = ['XM68M6',  # COVID-19 vaccine
             'XM1NL1',  # COVID-19 vaccine, inactivated virus
             'XM5DF6',  # COVID-19 vaccine, live attenuated virus
             'XM9QW8',  # COVID-19 vaccine, non-replicating viral vector
             'XM0CX4',  # COVID-19 vaccine, replicating viral vector
             'XM5JC5',  # COVID-19 vaccine, virus protein subunit
             'XM1J92',  # COVID-19 vaccine, virus-like particle (VLP)
             'XM6AT1',  # COVID-19 vaccine, DNA based
             'XM0GQ8',  # COVID-19 vaccine, RNA based
             ]

VDS_DISEASE = 'RA01'



def fully_vaccinated(line):
    if line in FULLY_VACCINATED_YES:
        return True
    if line in FULLY_VACCINATED_NO:
        return False
    status = COVID_ALL.search(line)
    if status:
        return status.group(1) is None
    return None


def name_fixer(vax_name):
    vax_name = vax_name.strip()
    if vax_name in VACCINES:
        return vax_name
    rf = rapidfuzz.process.extractOne(vax_name, VACCINES.keys(), score_cutoff=90)
    print("RapidFuzz Used '", vax_name, "'", rf)
    if rf:
        return rf[0]
    return vax_name


def parse_image(img_path, **kwargs):
    if type(img_path) is Image:
        img = img_path
    else:
        img = Image.open(img_path, **kwargs)
    vax = None

    text = pytesseract.image_to_string(img)

    fully = fully_vaccinated(text)

    ios_wallet = COVID_IOS.search(text)
    if ios_wallet:
        vax = ios_wallet.groups()
        vax_name = name_fixer(vax[0])
        vax_code = VACCINES.get(vax_name)
        vax = [(vax_name, vax_code, vax[1]), (vax_name, vax_code, vax[2])]
        print(vax)


    ihs_statement = IHS_STATEMENT.findall(text)
    if ihs_statement:
        print('ihs certificate found')
        vax = [(name_fixer(v[1]), VACCINES.get(name_fixer(v[1])), v[0]) for v in ihs_statement]


    if vax and any([v[1] is None for v in vax]):
        print("WARNING: Vax code empty", vax)

    vrecord = {'required_vaccinations': fully, 'vax': vax}
    return vrecord


def parse_cis(pp):
    contents = pp.pages[0].extract_text().split('\n')
    person_name = contents[3]  # contents[3]: JABBA T HUTT 01 Jan 1990
    person_name = ' '.join(person_name.split(' ')[:-3])  # Strips off the date

    # If you have a long name
    if contents[5] == 'Individual Healthcare Identifier (IHI) Document number':
        person_name = person_name + contents[4]
        contents.pop(4)

    # contents[9]: 'AstraZeneca Vaxzevria 27 Aug 2021, 07 Oct 2021'
    # contents[9]: 'COVID-19 Vaccine  01 Apr 2021, 01 Jul 2021'
    vaxes = DIGITAL_CERTIFICATE_VACCINE.findall('\n'.join(contents[9:]))
    dates = list()
    for line in vaxes:
        name = line[0].strip()
        # this occurs if you have an earlier CIS where it was known as 'COVID-19 Vaccine AstraZeneca'
        # just give them the new name and be donewith it
        if name == 'Vaccine':
            print("Assuming AZ", contents[10])
            name = 'AstraZeneca Vaxzevria'
        code = VACCINES.get(name)
        dates.extend([(name, code, d) for d in line[1:] if d])


    if contents[10] != 'Disclaimer' and contents[10] != 'AstraZeneca':
        print("WARNING: Disclaimer not in line 10", contents[10])

    all_doses = fully_vaccinated(contents[1])

    vrecord = {'name': person_name, 'vax': dates,
               'required_vaccinations': all_doses, 'source': 'CIS'}
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

    vrecord = {'name': person_name, 'vax': vax, 'required_vaccinations': all_doses, 'source': 'IHS'}
    if len(vax):
        return vrecord
    else:
        print("WARNING: No COVID-19 Vaccines given?")
        return {}

def parse_vds_nc(f,**kwargs):
    if type(f) is Image:
        img = f
    else:
        img = Image.open(f, **kwargs)
    qre = pyzbar.decode(img)

    if not qre:
        return {}
    try:
        qrdata = json.loads(qre[0].data)['data']
    except ValueError as e:
        print(e)
        return {}

    name = qrdata['msg']['pid']['n']
    vaccines = qrdata['msg']['ve']
    dates = list()
    for v in vaccines:
        if v['des'] not in VDS_CODES and not VDS_DISEASE.startswith(VDS_DISEASE):
            continue
        vax_name = v['nam']
        code = VACCINES.get(vax_name)
        dates.extend([(vax_name, code, dose['dvc']) for dose in v['vd']])
    vrecord = {'name': name, 'vax': dates, 'required_vaccinations': None, 'source': 'VDS-NC'}
    return vrecord

def parse_vds_nc_pdf(f):
    doc = fitz.open("pdf", f)
    px = fitz.Pixmap(doc, doc.getPageImageList(0)[0][0])
    return parse_vds_nc(io.BytesIO(px.getImageData("png")))

# TODO: rename
def any_except_none(items, return_value=False):
    if not items:
        return None
    a = any(items)
    if return_value and a:
        return items
    elif return_value:
        return None

    return a


def get_images_from_pdf(img_path):
    doc = fitz.open("pdf", img_path)
    records = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        vrecord = parse_image(io.BytesIO(pix.pil_tobytes(format='png')))
        vr2 = parse_vds_nc(io.BytesIO(pix.pil_tobytes(format='png')))
        records.append(vrecord)
        if vr2:
            records.append(vr2)

    rv = [q['required_vaccinations'] for q in records if q['required_vaccinations'] is not None]
    vax = list(itertools.chain.from_iterable([q['vax'] for q in records if q['vax'] is not None]))

    return {'required_vaccinations': any_except_none(rv), 'vax': any_except_none(vax, True), 'name': None,
            'source': 'OCR'}


def parse(f, **kwargs):
    try:
        pp = pdfplumber.open(f)
    except TypeError:  # sometimes, it just dies
        return {}
    except PDFSyntaxError: # Occurs where an image file is used as input
        vrecord = parse_image(f)
        vrecord['name'] = None
        vds_record = parse_vds_nc(f)
        if vds_record:
            return vds_record
        if all(v is None for v in (vrecord['required_vaccinations'], vrecord['vax'])):
            return {}
        return vrecord
    except:
        return {}
    contents = pp.pages[0].extract_text()
    if contents:
        contents = contents.split('\n')
        if len(contents) == 1: return {}
    else:
        print("PARSING IMAGE")
        #TODO: Not sure how to handle where you can't parse any data out of the image
        result = get_images_from_pdf(f)
        if all(v is None for v in (result['required_vaccinations'], result['vax'])):
            return {}
        return result
    if contents[0] == 'COVID-19 digital certificate':
        return parse_cis(pp)
    elif contents[0] == 'Immunisation history statement' or contents[1] == 'Immunisation history statement':
        return parse_ihs(pp)
    elif contents[0] == 'International COVID-19 Vaccination Certificate':
        return parse_vds_nc_pdf(f)
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
    pdfs = glob.glob("examples/*.pdf")
    for pdf in pdfs:
        print(pdf)
        pdf = io.BytesIO(open(pdf, 'rb').read())
        print(parse(pdf))
    json.dump(jabba, open('vax.json', 'w'))
