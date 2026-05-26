MALAWI_TAS_BY_REGION = {
    "Central": {
        "Lilongwe": ["Chitukula", "Chadza", "Kalolo", "Masula", "Mtema", "Njewa", "Tsabango"],
        "Dedza": ["Chauma", "Kachere", "Kaphuka", "Kasumbu", "Kamenyagwaza", "Tambala"],
        "Dowa": ["Chakhaza", "Dzoole", "Mkukula", "Msakambewa", "Mponela", "Nsakambewa"],
        "Kasungu": ["Chulu", "Kaomba", "Kapelula", "Mwase", "Santhe", "Simlemba"],
        "Mchinji": ["Dambele", "Mlonyeni", "Mavwere", "Mkanda", "Nyoka", "Zulu"],
        "Ntcheu": ["Champiti", "Goodson Ganya", "Kwataine", "Makwangwala", "Masasa", "Mpando"],
        "Nkhotakota": ["Kafuzira", "Mwadzama", "Mphonde", "Mwansambo", "Malengachanzi"],
        "Ntchisi": ["Chikho", "Kalumo", "Kasakula", "Malenga", "Nthondo"],
        "Salima": ["Kambwiri", "Kalonga", "Khombedza", "Kuluunda", "Maganga", "Ndindi"],
    },
    "Southern": {
        "Blantyre": ["Kapeni", "Kuntaja", "Lundu", "Machinjiri", "Somba"],
        "Zomba": ["Chikowi", "Kuntumanji", "Mlumbe", "Mponda", "Mwambo"],
        "Mangochi": ["Bwananyambi", "Chowe", "Chimwala", "Jalasi", "Katuli", "Makanjira", "Mponda", "Namabvi"],
        "Mulanje": ["Chikumbu", "Juma", "Laston Njema", "Mabuka", "Mkanda", "Nkanda"],
        "Thyolo": ["Bvumbwe", "Changata", "Kapichi", "Khwethemule", "Mphuka", "Nanseta"],
        "Chiradzulu": ["Kadewere", "Likoswe", "Mpama", "Nkalo", "Ntchema"],
        "Machinga": ["Chikweo", "Chamba", "Kawinga", "Liwonde", "Mposa", "Nkoola"],
        "Balaka": ["Amidu", "Chanthunya", "Kalembo", "Nkaya", "Nsamala", "Phalula"],
        "Chikwawa": ["Chapananga", "Katunga", "Lundu", "Makhuwira", "Ngabu"],
        "Nsanje": ["Chimombo", "Malemia", "Mbenje", "Ndamera", "Tengani"],
        "Phalombe": ["Chiwalo", "Jenala", "Kaduya", "Nazombe", "Nkhulambe"],
        "Mwanza": ["Kanduku", "Nthache", "Govati"],
        "Neno": ["Chekucheku", "Dambe", "Mlauli", "Symon"],
    },
    "Northern": {
        "Mzuzu": ["Mzuzu City"],
        "Mzimba": ["Chindi", "Jalavikuwa", "Khosolo", "Mabulabo", "M'mbelwa", "Mpherembe"],
        "Rumphi": ["Chikulamayembe", "Katumbi", "Mwahenga", "Mwankhunikira", "Zolokere"],
        "Karonga": ["Kilupula", "Kyungu", "Mwakaboko", "Mwirang'ombe", "Wasambo"],
        "Chitipa": ["Kameme", "Mwaulambia", "Nthalire", "Wenya", "Yamba"],
        "Nkhata Bay": ["Bogoyo", "Kabunduli", "Mkondowe", "Malanda", "Mankhambira"],
        "Likoma": ["Likoma", "Chizumulu"],
    },
}


DISTRICTS_BY_REGION = {
    region: list(districts.keys()) for region, districts in MALAWI_TAS_BY_REGION.items()
}
