# Digital Certificate Parser

Given a COVID-19 Digital Certificate,  Individual Health Summary or an International COVID-19 Vaccination Certificate (VDS-NC), print out vaccine details and dates.

    {"name": "JABBA T HUTT",
      "vax": [
        ["AstraZeneca Vaxzevria", "COVAST", "01 Apr 2021"],
        ["AstraZeneca Vaxzevria", "COVAST", "22 Jul 2021"]
      ],
      "required_vaccinations": true}

### Known Issues:
- [ ] Hasn't been tested with a digital certificate or IHS with
  - Janssen-Cilag (J&J)
  - Any of the "recognised" but not "registered" vaccines [see TGA](https://www.tga.gov.au/covid-19-vaccines-not-registered-australia-current-international-use-tga-advice-recognition)
- [x] Handlea  digital certificate with a different first and second brand
- [x] Handle third doses
  - The C19 digital certificate just has the first two doses
- [ ] doesn't say if a person is considered 'fully vaccinated' if their IHS version is early enough not to include the tick 
- [ ] code quality is pretty terrible
- [ ] VDS-NC certificates aren't validated 