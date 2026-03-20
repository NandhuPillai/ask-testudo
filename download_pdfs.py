"""
Download all UMD undergraduate program PDFs from the academic catalog.
Each program page has a PDF link following the pattern: {page_url}/{slug}.pdf
"""
import os
import time
import requests
from urllib.parse import urlparse
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# All program page URLs (Majors, Minors, Certificates)
PROGRAM_URLS = [
    # === MAJORS ===
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/accounting/accounting-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/business/accounting/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/aerospace-engineering/aerospace-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/african-american-africana-studies/african-american-africana-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/agricultural-resource-economics/agricultural-resource-economics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/plant-sciences-landscape-architecture/agricultural-science-technology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/american-studies/american-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/animal-sciences/animal-sciences-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/anthropology/anthropology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/arabic-studies/arabic-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/architecture-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/art-history-archaeology/art-history-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/astronomy/astronomy-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/atmospheric-oceanic-science/atmospheric-oceanic-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/chemistry-biochemistry/biochemistry-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/bioengineering/biocomputational-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/engineering/biocomputational-engineering/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/bioengineering/bioengineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/biological-sciences/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/biological-sciences/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/chemical-biomolecular-engineering/chemical-biomolecular-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/chemistry-biochemistry/chemistry-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/chinese/chinese-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/cinema-media-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/cinema-media-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/civil-environmental-engineering/civil-environmental-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/classical-languages-literature/classics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/communication/communication-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/communication/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/electrical-and-computer/computer-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/computer-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/criminology-criminal-justice/criminology-criminal-justice-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/behavioral-social-sciences/criminology-criminal-justice-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/electrical-and-computer/cyber-physical-systems-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/engineering/cyber-physical-systems-engineering/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/theatre-dance-performance-studies/dance-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/human-development-quantitative-methodology/early-childhood-special-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/economics/economics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/electrical-and-computer/electrical-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/elementary-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/counseling-higher-special-education/elementary-middle-special-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/english-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/environmental-science-policy/environmental-science-policy-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/environmental-science-technology/environmental-science-technology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/family-science/family-health-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/nutrition-food-science/fermentation-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/fermentation-science/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/finance/finance-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/fire-protection-engineering/fire-protection-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/french-language-literature/french-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/geographical-sciences/geographical-sciences-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/geology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/germanic-studies/german-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/global-environmental-occupational-health/global-health-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/government-politics/government-politics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/hearing-speech-sciences/hearing-speech-sciences-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/history/history-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/human-development-quantitative-methodology/human-development-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/art/immersive-media-design-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/immersive-media-design-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/individual-studies/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/information-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/information/information-science/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/decision-operations-information-technologies/information-systems-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/logistics-business-public-policy/international-business-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/government-politics/international-relations-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/italian-studies/italian-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/japanese/japanese-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/jewish-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/journalism/journalism-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/kinesiology/kinesiology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/plant-sciences-landscape-architecture/landscape-architecture-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/linguistics/linguistics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/management/management-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/business/management/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/marketing/marketing-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/business/marketing/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/materials-science-engineering/materials-science-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/mathematics/mathematics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/mechanical-engineering/mechanical-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/aerospace-engineering/mechatronics-engineering-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/engineering/mechatronics-engineering/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/middle-school-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/music/music-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/psychology/neuroscience-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/biology/neuroscience-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/nutrition-food-science/nutrition-food-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/decision-operations-information-technologies/operations-management-business-analytics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/persian-studies/persian-studies-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/philosophy/philosophy-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/philosophy/philosophy-politics-economics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/physics/physics-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/plant-sciences-landscape-architecture/plant-sciences-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/psychology/psychology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/behavioral-community-health/public-health-practice-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/public-health-science/public-health-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/public-health-science/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/public-policy-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/real-estate-built-environment-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/religions-ancient-middle-east-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/romance-languages/romance-languages-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/russian-language-literature/russian-language-literature-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/art-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/english-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/mathematics-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/science-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/social-studies-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/world-language-education-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/social-data-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/social-data-science-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/sociology/sociology-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/spanish-language-literatures-culture/spanish-language-literatures-culture-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/art/art-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/logistics-business-public-policy/supply-chain-management-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/technology-info-design-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/theatre-dance-performance-studies/theatre-major/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/women-gender-sexuality-studies/womens-gender-sexuality-studies-major/",

    # === MINORS ===
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/mathematics/actuarial-mathematics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/advanced-cybersecurity-experience-students-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/african-american-africana-studies/african-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/plant-sciences-landscape-architecture/agricultural-science-technology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/african-american-africana-studies/anti-black-racism-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/arabic-studies/arabic-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/art-history-archaeology/archaeology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/classical-languages-literature/archaeology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/army-leadership-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/art-history-archaeology/art-history-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/theatre-dance-performance-studies/arts-leadership-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/asian-american-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/astronomy/astronomy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/atmospheric-oceanic-science/atmospheric-chemistry-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/atmospheric-oceanic-science/atmospheric-sciences-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/women-gender-sexuality-studies/black-womens-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/african-american-africana-studies/black-womens-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/business-analytics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/chinese/chinese-language-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/classical-languages-literature/classical-mythology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/computational-finance-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/computational-finance-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/electrical-and-computer/computer-engineering-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/computer-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/construction-project-management-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/civil-environmental-engineering/construction-project-management-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/creative-placemaking-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/creative-placemaking-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/creative-writing-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/behavioral-social-sciences/criminal-justice-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/data-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/mathematics/data-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/sociology/demography-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/digital-storytelling-poetics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/counseling-higher-special-education/disability-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/earth-history-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/earth-material-properties-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/economics/economics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/education-policy-equity-justice-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/education-policy-equity-justice-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/entomology/entomology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/entrepreneurial-leadership-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/french-language-literature/french-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/business/general-business-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/geochemistry-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/geographical-sciences/geographic-information-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/geophysics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/germanic-studies/german-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/global-engineering-leadership-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/agricultural-resource-economics/global-poverty-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/global-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/global-terrorism-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/classical-languages-literature/greek-language-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/hearing-speech-sciences/hearing-speech-sciences-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/hebrew-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/hebrew-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/history-theory-architecture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/history/history-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/human-development-quantitative-methodology/human-development-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/humanities-health-medicine-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/hydrology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/information-risk-management-ethics-privacy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/information/information-risk-management-ethics-privacy/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/government-politics/international-development-conflict-management-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/israel-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/italian-studies/italian-language-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/japanese/japanese-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/jewish-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/kinesiology/kinesiology-biomechanics-motor-control-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/kinesiology/kinesiology-exercise-physiology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-health/kinesiology/kinesiology-sport-commerce-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/korean-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/plant-sciences-landscape-architecture/landscape-management-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/latin-american-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/classical-languages-literature/latin-language-literature-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/law-society-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/counseling-higher-special-education/leadership-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/women-gender-sexuality-studies/lesbian-gay-bisexual-transgender-studies/lesbian-gay-bisexual-transgender-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/linguistics/linguistics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/mathematics/mathematics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/journalism/media-technology-democracy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/atmospheric-oceanic-science/meteorology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/history/middle-eastern-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/military-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/music/music-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/music/music-performance-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/nanoscale-science-technology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/undergraduate-studies/naval-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/psychology/neuroscience-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/nonprofit-leadership-and-social-innovation-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/mechanical-engineering/nuclear-engineering-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/entomology/paleobiology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/paleobiology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/persian-studies/persian-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/philosophy/philosophy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/physics/physics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/astronomy/planetary-sciences-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/planetary-sciences-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/portuguese-brazilian-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/professional-writing-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/civil-environmental-engineering/project-management-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/public-leadership-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/electrical-and-computer/quantum-science-engineering-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/architecture-planning-preservation/real-estate-development-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/jewish-studies/religious-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/geographical-sciences/remote-sensing-environmental-change-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/communication/rhetoric-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/english-language-literature/rhetoric-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/computer-science/robotics-autonomous-systems-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/robotics-autonomous-systems-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/russian-language-literature/russian-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/science-technology-ethics-policy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/science-technology-ethics-policy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/science-technology-ethics-policy-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/secondary-education-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/sociology/sociology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/environmental-science-technology/soil-science-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/spanish-language-literatures-culture/spanish-literature-linguistics-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/spanish-language-literatures-culture/spanish-language-culture-professional-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/spanish-language-literatures-culture/spanish-heritage-language-latino-culture-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/mathematics/statistics-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/computer-mathematical-natural-sciences/geology/surficial-geology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/survey-methodology-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/environmental-science-policy/sustainability-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/public-policy/sustainability-studies-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/tesol-education-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/engineering/technology-entrepreneurship-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/information/technology-innovation-leadership-minor/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/universities-shady-grove/information/technology-innovation-leadership/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/american-studies/us-latina-latino-studies-minor/",

    # === CERTIFICATES ===
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/behavioral-social-sciences/african-american-africana-studies/african-american-africana-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/applied-agriculture/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/history/east-asian-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/languages-literatures-cultures/east-asian-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/agriculture-natural-resources/international-agriculture-natural-resources-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/latin-american-caribbean-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/counseling-higher-special-education/leadership-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/women-gender-sexuality-studies/lesbian-gay-bisexual-transgender-studies/LGBTQ-studies-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/education/teaching-learning-policy-leadership/secondary-education-certificate/",
    "https://academiccatalog.umd.edu/undergraduate/colleges-schools/arts-humanities/women-gender-sexuality-studies/women-gender-sexuality-studies-certificate/",
]

def get_pdf_url_and_filename(page_url):
    """
    Given a page URL, construct the PDF download URL and a unique filename.
    Pattern: {page_url}/{slug}.pdf
    For duplicate slugs, prefix with parent path components.
    """
    parsed = urlparse(page_url)
    path = parsed.path.rstrip("/")
    slug = path.split("/")[-1]
    pdf_url = f"{page_url}{slug}.pdf"
    return pdf_url, slug

def make_unique_filenames(urls):
    """Handle duplicate slugs by prefixing with parent directory names."""
    slugs = []
    for url in urls:
        _, slug = get_pdf_url_and_filename(url)
        slugs.append(slug)
    
    # Count occurrences
    counts = Counter(slugs)
    
    # For duplicates, create unique names using parent path
    seen = Counter()
    result = []
    for url, slug in zip(urls, slugs):
        if counts[slug] > 1:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            parts = path.split("/")
            # Use the parent directory as prefix for disambiguation
            if len(parts) >= 2:
                parent = parts[-2]
                unique_name = f"{parent}--{slug}"
            else:
                seen[slug] += 1
                unique_name = f"{slug}--{seen[slug]}"
        else:
            unique_name = slug
        
        pdf_url, _ = get_pdf_url_and_filename(url)
        result.append((pdf_url, f"{unique_name}.pdf", url))
    
    return result

def download_pdf(pdf_url, filepath, timeout=30):
    """Download a PDF file from the given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
    response.raise_for_status()
    
    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return os.path.getsize(filepath)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    entries = make_unique_filenames(PROGRAM_URLS)
    total = len(entries)
    
    print(f"Starting download of {total} PDFs to {DATA_DIR}")
    print("=" * 60)
    
    success = 0
    failed = []
    
    for i, (pdf_url, filename, page_url) in enumerate(entries, 1):
        filepath = os.path.join(DATA_DIR, filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            print(f"[{i}/{total}] SKIP (exists): {filename}")
            success += 1
            continue
        
        try:
            size = download_pdf(pdf_url, filepath)
            size_kb = size / 1024
            print(f"[{i}/{total}] OK: {filename} ({size_kb:.1f} KB)")
            success += 1
        except Exception as e:
            print(f"[{i}/{total}] FAIL: {filename} - {e}")
            failed.append((filename, pdf_url, str(e)))
            # Clean up partial download
            if os.path.exists(filepath):
                os.remove(filepath)
        
        # Small delay to be respectful to the server
        time.sleep(0.3)
    
    print("\n" + "=" * 60)
    print(f"Download complete: {success}/{total} succeeded")
    
    if failed:
        print(f"\n{len(failed)} FAILED downloads:")
        for fname, url, err in failed:
            print(f"  - {fname}: {err}")
            print(f"    URL: {url}")

if __name__ == "__main__":
    main()
