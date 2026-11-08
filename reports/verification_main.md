# Main corpus source verification

150 claims, 30 per domain; 140 distinct URLs. Sources were opened and reviewed by agents. This is not independent human review, and a stored verified flag alone is not evidence of truth. Original and revised wording is retained in the JSONL ledger.

Difficulty uses the prospective rubric in main_protocol.md. It is a proxy judgment, not an empirical score of model knowledge.

Three text-similarity candidates at ≥0.75 all came from the retained pilot: geo_001/geo_004 (different countries), sci_001/sci_007 (different elements), tech_002/tech_008 (different numeral systems). These share templates but express different facts; they were retained. No newly added pair crossed this threshold. Semantic review also checked propositions and topical variety.

| Claim | Verified replacement answer | Source | Evidence locator |
| --- | --- | --- | --- |
| geo_001 | Ottawa | [Settling in Canada - Land and climate](<https://www.canada.ca/en/immigration-refugees-citizenship/services/settle-canada/land-climate.html>) | Cities, provinces and regions |
| geo_002 | Canberra | [Establishing the nation's capital](<https://www.parliament.act.gov.au/visit-and-learn/learn/resources/fs/establishing-the-nations-capital>) | Finding the right site; Creating Canberra |
| geo_003 | Brasilia | [Brasília - DF](<https://www.gov.br/g20/pt-br/sobre-o-g20/cidades-sede/brasilia-df>) | Informações básicas |
| geo_004 | Tokyo | [About Japan](<https://www.japan.go.jp/japan/index.html>) | Capital Tokyo |
| geo_005 | Cairo | [Egypt Toponymic Factfile](<https://assets.publishing.service.gov.uk/media/6a33d3bf25c5199bda117789/Egypt_Toponymic_Factfile.pdf>) | PDF page 1, footnote 4 |
| geo_006 | Rabat | [Rabat, a capital to live in](<https://www.visitmorocco.com/en/travel/rabat>) | Rabat, a modern capital with deep-rooted history; Sport in Rabat |
| geo_007 | Tanzania | [Kilimanjaro National Park](<https://whc.unesco.org/en/list/403/>) | Description; property country; Integrity |
| geo_008 | Mediterranean Sea | [Nile River in Black and White](<https://science.nasa.gov/resource/nile-river-in-black-and-white/>) | Image description |
| geo_009 | Atlantic Ocean | [Facts about the Nordic countries](<https://www.norden.org/en/information/facts-about-nordic-countries>) | Facts about Iceland |
| geo_010 | Spain | [Main destinations in Spain](<https://www.spain.info/en/destinations/>) | Explore Spain; city list |
| sci_001 | O | [Introduction to Chemistry, Flames and Radiation](<https://books.rsc.org/books/monograph/2382/chapter/8716357/Introduction-to-Chemistry-Flames-and-Radiation>) | Discussion of atoms and molecules |
| sci_002 | six | [Carbon - Element information, properties and uses](<https://periodic-table.rsc.org/element/6/carbon>) | Atomic number glossary; Fact box |
| sci_003 | third | [Facts About Earth](<https://science.nasa.gov/earth/facts/>) | Namesake; Formation |
| sci_004 | 0 degrees Celsius | [Freezing point depression and boiling point elevation: the effects of solutes and of pressure](<https://www.animations.physics.unsw.edu.au/jw/freezing-point-depression-boiling-point-elevation.htm>) | Why do substances melt and boil?; The effects of solutes; Further complications |
| sci_005 | ohm | [NIST Guide to the SI, Chapter 4: The Two Classes of SI Units and the SI Prefixes](<https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-4-two-classes-si-units-and-si-prefixes>) | Table 3, electric resistance |
| sci_006 | thymine | [Base Pair](<https://www.genome.gov/genetics-glossary/Base-Pair>) | Definition |
| sci_007 | Au | [Gold - Element information, properties and uses](<https://periodic-table.rsc.org/element/79/Gold>) | Chemistry in its element: gold |
| sci_008 | kilogram | [NIST Guide to the SI, Chapter 4: The Two Classes of SI Units and the SI Prefixes](<https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-4-two-classes-si-units-and-si-prefixes>) | Table 1, mass |
| sci_009 | two | [Helium - Element information, properties and uses](<https://periodic-table.rsc.org/element/2/helium>) | Atomic number glossary; Fact box |
| sci_010 | Mercury | [Mercury](<https://science.nasa.gov/Mercury/>) | Mercury Facts |
| his_001 | 1969 | [Apollo 11 Mission Overview](<https://www.nasa.gov/missions/apollo/apollo-11/apollo-11-mission-overview/>) | Mission Highlights |
| his_002 | 1776 | [The Declaration of Independence: A History](<https://www.archives.gov/founding-docs/declaration-history>) | The Committee of Five |
| his_003 | 1066 | [History of Battle Abbey and Battlefield](<https://www.english-heritage.org.uk/visit/places/1066-battle-of-hastings-abbey-and-battlefield/history-and-stories/history/>) | Opening paragraph |
| his_004 | 1215 | [Magna Carta](<https://www.parliament.uk/magnacarta/>) | When was Magna Carta first issued? |
| his_005 | 1789 | [Summoning of the Estates General, 1789](<https://en.chateauversailles.fr/discover/history/key-dates/summoning-estates-general-1789>) | Opening paragraph |
| his_006 | 1912 | [RMS Titanic facts](<https://www.rmg.co.uk/stories/maritime-history/rms-titanic-facts?open=>) | RMS Titanic timeline |
| his_007 | 1453 | [The Art of the Ottomans before 1600](<https://www.metmuseum.org/essays/the-art-of-the-ottomans-before-1600>) | Historical overview |
| his_008 | 1896 | [Olympic flame handed over in Athens as it begins journey to Italy for Milano Cortina 2026](<https://newsroom.olympics.com/record/1676>) | Opening paragraph |
| his_009 | 1815 | [Battle of Waterloo](<https://www.nam.ac.uk/explore/battle-waterloo>) | Timeline: 18 June 1815 |
| his_010 | 1945 | [80 Years Since the End of World War II](<https://visit.archives.gov/whats-on/explore-exhibits/80-years-end-world-war-ii>) | Featured Document |
| tech_001 | Guido van Rossum | [History and License](<https://docs.python.org/3.10/license.html>) | History of the software |
| tech_002 | two | [2. Lexical analysis](<https://docs.python.org/3/reference/lexical_analysis.html>) | Integer literals |
| tech_003 | 32 | [RFC 791: Internet Protocol](<https://www.rfc-editor.org/rfc/rfc791.html>) | Addressing; Source Address; Destination Address |
| tech_004 | Hypertext Markup Language | [Introduction to HTML 4](<https://www.w3.org/TR/html401/intro/intro.html>) | 2.2 What is HTML? |
| tech_005 | Cascading Style Sheets | [Cascading Style Sheets home page](<https://www.w3.org/Style/CSS/Overview.en.html>) | What is CSS? |
| tech_006 | Domain Name System | [RFC 1034: Domain Names - Concepts and Facilities](<https://www.rfc-editor.org/rfc/rfc1034.html>) | 1. Status of this memo |
| tech_007 | Central Processing Unit | [What is a central processing unit (CPU)?](<https://www.ibm.com/think/topics/central-processing-unit>) | Definition |
| tech_008 | sixteen | [2. Lexical analysis](<https://docs.python.org/3/reference/lexical_analysis.html>) | Integer literals |
| tech_009 | 65 | [RFC 3072: Structured Data Exchange Format (SDXF)](<https://www.rfc-editor.org/rfc/rfc3072.html>) | Character representation; page 8 |
| tech_010 | Linus Torvalds | [A Short History of Git](<https://git-scm.com/book/en/v2/Getting-Started-A-Short-History-of-Git>) | 2005 origins of Git |
| gen_001 | three | [Triangle](<https://mathworld.wolfram.com/Triangle.html>) | Definition |
| gen_002 | six | [Hexagon](<https://mathworld.wolfram.com/Hexagon.html>) | Definition |
| gen_003 | 60 | [NIST Guide to the SI, Chapter 5: Units Outside the SI](<https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si>) | Table 6, hour |
| gen_004 | 366 | [Calendars from around the world](<https://www.rmg.co.uk/sites/default/files/Calendars-from-around-the-world.pdf>) | PDF page 15, Gregorian calendar |
| gen_005 | 64 | [FIDE Laws of Chess taking effect from 1 January 2023](<https://handbook.fide.com/chapter/e012023>) | Article 2.1 |
| gen_006 | 88 | [Why Aren't There More Than 88 Keys on a Piano?](<https://hub.yamaha.com/pianos/p-acoustic/why-arent-there-more-than-88-keys-on-a-piano/>) | Modern keyboard discussion |
| gen_007 | Jane Austen | [Pride and Prejudice](<https://janeaustens.house/jane-austen/novels/pride-and-prejudice/>) | Opening paragraph and publication history |
| gen_008 | William Shakespeare | [Hamlet](<https://www.folger.edu/explore/shakespeares-works/hamlet/>) | Introduction to the play |
| gen_009 | ten | [Roman Numerals](<https://mathworld.wolfram.com/RomanNumerals.html>) | Roman character and numerical value table |
| gen_010 | twelve | [Dozen Definition & Meaning](<https://www.merriam-webster.com/dictionary/dozen>) | Definition 1; Kids Definition |
| geo_011 | Pacific Ocean | [What is the largest ocean basin on Earth?](<https://oceanservice.noaa.gov/facts/biggestocean.html>) | Opening heading and basin ranking |
| geo_012 | Arctic Ocean | [What is the world's smallest ocean?](<https://oceanservice.noaa.gov/facts/smallestocean.html>) | Opening heading |
| geo_013 | 0 degrees | [What is latitude?](<https://oceanservice.noaa.gov/facts/latitude.html>) | Latitude lines and equator explanation |
| geo_014 | forward one day | [Z-time (Coordinated Universal Time)](<https://www.noaa.gov/jetstream/time>) | Paragraph on crossing the International Date Line |
| geo_015 | 0 degrees | [Z-time (Coordinated Universal Time)](<https://www.noaa.gov/jetstream/time>) | 1884 meridian convention paragraph |
| geo_016 | Pacific Ocean | [Planet Postcard: The Mariana Trench](<https://www.ncei.noaa.gov/news/planet-postcard-mariana-trench>) | A Trench of Epic Proportions |
| geo_017 | Lake Baikal | [Lake Baikal](<https://whc.unesco.org/en/list/754/>) | Description and justification for inscription |
| geo_018 | South America | [Desert Dust Feeds Amazon Forests](<https://science.nasa.gov/science-research/earth-science/29apr_amazondust/>) | Opening comparison of Sahara and Amazon |
| geo_019 | Pacific coast | [Topography of South America](<https://science.nasa.gov/earth/earth-observatory/topography-of-south-america-3581/>) | Topographic relief paragraph |
| geo_020 | Africa | [Desert Dust Feeds Amazon Forests](<https://science.nasa.gov/science-research/earth-science/29apr_amazondust/>) | Opening Sahara paragraph |
| geo_021 | Australia | [Great Barrier Reef](<https://whc.unesco.org/en/list/154/>) | English description |
| geo_022 | Ecuador | [Galapagos Islands](<https://whc.unesco.org/en/list/1/>) | Country listing and protection requirements |
| geo_023 | glaciers | [U-Shaped Valleys, Fjords, and Hanging Valleys](<https://www.nps.gov/articles/ushapedvalleysfjordshangingvalleys.htm>) | Fjords section |
| geo_024 | deposition | [Delta Landforms](<https://home.nps.gov/articles/delta-landforms.htm>) | Opening delta-formation explanation |
| geo_025 | saltwater lake | [Dead Sea](<https://science.nasa.gov/earth/earth-observatory/dead-sea-6136/>) | Lake basin and evaporation paragraphs |
| geo_026 | Mount Everest | [Sagarmatha National Park](<https://whc.unesco.org/en/list/120/>) | English description |
| geo_027 | Antarctica | [Frequently Asked Questions About Antarctica](<https://www.nasa.gov/frequently-asked-questions-about-antarctica/>) | What is Antarctica? |
| geo_028 | Red Sea | [About Suez Canal](<https://www.suezcanal.gov.eg/English/About/SuezCanal/Pages/AboutSuezCanal.aspx>) | Opening canal description |
| geo_029 | Pacific Ocean | [Connectivity](<https://pancanal.com/en/connectivity/>) | Connectivity bullet on cargo transport |
| geo_030 | three | [Lake Victoria South Basin Area](<https://wra.go.ke/lake-victoria-south-basin-area/>) | Paragraph distinguishing lake and drainage basin |
| sci_011 | proteins | [Ribosome](<https://www.genome.gov/genetics-glossary/Ribosome>) | Definition and narration |
| sci_012 | ATP | [Mitochondria](<https://www.genome.gov/genetics-glossary/Mitochondria>) | Definition |
| sci_013 | ribose | [Ribonucleic Acid (RNA)](<https://www.genome.gov/genetics-glossary/Ribonucleic-Acid-RNA>) | Definition |
| sci_014 | 46 | [Chromosome](<https://www.genome.gov/genetics-glossary/Chromosome>) | Definition |
| sci_015 | pancreas | [What Is Diabetes?](<https://www.niddk.nih.gov/health-information/diabetes/overview/what-is-diabetes>) | Introductory insulin definition |
| sci_016 | nephrons | [Your Kidneys & How They Work](<https://www.niddk.nih.gov/health-information/kidney-disease/kidneys-how-they-work>) | How do my kidneys work? |
| sci_017 | small intestine | [Your Digestive System & How it Works](<https://www.niddk.nih.gov/health-information/digestive-diseases/digestive-system-how-it-works>) | What happens to the digested food? |
| sci_018 | six | [What Is an Insect?](<https://naturalhistory.si.edu/education/teaching-resources/life-science/what-insect>) | Teaching transcript on shared insect features |
| sci_019 | green | [What in earth? Understanding what fungi really are](<https://www.kew.org/read-and-watch/what-is-fungi>) | Spot the difference |
| sci_020 | chitin | [The wonderful world of fungi](<https://www.kew.org/read-and-watch/the-wonderful-world-of-fungi>) | How fungi differ from plants |
| gen_011 | Leonardo da Vinci | [From the 'Mona Lisa' to 'The Wedding Feast at Cana' - The Salle des Etats](<https://www.louvre.fr/en/explore/the-palace/from-the-mona-lisa-to-the-wedding-feast-at-cana>) | Mona Lisa artwork credit |
| gen_012 | Vincent van Gogh | [Vincent van Gogh. The Starry Night. Saint Remy, June 1889](<https://www.moma.org/collection/works/79802>) | Work title and artist credit |
| gen_013 | Pyotr Ilyich Tchaikovsky | [Pyotr Il'yich Tchaikovsky](<https://www.rbo.org.uk/people/pyotr-ilyich-tchaikovsky>) | Biography listing ballet scores |
| gen_014 | four | [The Structure of the Violin: The structure of the strings](<https://www.yamaha.com/en/musical_instrument_guide/violin/mechanism/mechanism002.html>) | Opening explanation of violin strings |
| gen_015 | woodwind family | [Musical Instrument Guide](<https://www.yamaha.com/en/musical_instrument_guide/>) | Instrument families: Woodwinds |
| gen_016 | Miguel de Cervantes | [Don Quijote de la Mancha. Primera parte. Portada.](<https://cvc.cervantes.es/literatura/clasicos/quijote/edicion/parte1/portada/default.htm>) | Transcribed title page of the first part |
| gen_017 | George Orwell | [Nineteen Eighty-Four](<https://www.orwellfoundation.com/the-orwell-foundation/orwell/books-by-orwell/nineteen-eighty-four/>) | Book page in Books by Orwell |
| gen_018 | Japan | [Haiku](<https://poets.org/glossary/haiku>) | History of the haiku form |
| gen_019 | six | [About Braille](<https://www.loc.gov/nls/services-and-resources/informational-publications/about-braille/>) | Description of the braille cell |
| gen_020 | 40-40 | [Tennis Scoring: Points, Sets & Games](<https://www.usta.com/en/home/improve/tips-and-instruction/national/tennis-scoring-rules.html>) | Point scoring and deuce |
| gen_021 | six | [Basic Rules](<https://www.fivb.com/volleyball/the-game/basic-rules/>) | Basic team and court rules |
| gen_022 | 42.195 kilometers | [Disciplines at the GENERALI BERLIN-MARATHON](<https://www.generali-berlin-marathon.com/en/registration/disciplines>) | Disciplines over the marathon distance |
| gen_023 | shuttlecock | [BADMINTON Definition & Meaning](<https://www.merriam-webster.com/dictionary/badminton>) | Dictionary definition |
| gen_024 | 19 by 19 lines | [How to Play](<https://britgo.org/intro/intro2.html>) | Board size in introductory rules |
| gen_025 | 90 degrees | [Right Angle](<https://mathworld.wolfram.com/RightAngle.html>) | Definition |
| gen_026 | two | [Prime Number](<https://mathworld.wolfram.com/PrimeNumber.html>) | Definition and sequence of primes |
| gen_027 | seven | [Dice](<https://mathworld.wolfram.com/Dice.html>) | Opposite-face convention |
| gen_028 | fourteen | [Write a sonnet](<https://www.folger.edu/explore/write-a-sonnet/>) | Basic sonnet instructions |
| gen_029 | noun | [NOUN Definition & Meaning](<https://www.merriam-webster.com/dictionary/noun>) | Definition and kids definition |
| gen_030 | whole note | [ABRSM Music Theory Example Items reference sheets, Grade 5](<https://www.abrsm.org/sites/default/files/2023-09/abrsm-ot-reference-sheet-example-questions_online-music-theory-from-2020.pdf>) | PDF page 1: note values and American terms |
| his_011 | Tigris and Euphrates | [Art of the First Cities](<https://www.metmuseum.org/exhibitions/listings/2003/art-of-the-first-cities>) | Exhibition overview |
| his_012 | Olympia | [Archaeological Site of Olympia](<https://whc.unesco.org/en/list/517/>) | Brief description |
| his_013 | Qin Shi Huang | [Qin Dynasty (221-206 B.C.)](<https://www.metmuseum.org/essays/qin-dynasty-221-206-b-c>) | Opening paragraph |
| his_014 | royal tombs | [Memphis and its Necropolis - the Pyramid Fields from Giza to Dahshur](<https://whc.unesco.org/en/list/86/>) | Outstanding Universal Value |
| his_015 | Mount Vesuvius | [Archaeological Areas of Pompei, Herculaneum and Torre Annunziata](<https://whc.unesco.org/en/list/829/>) | Brief description |
| his_016 | Cuzco | [City of Cuzco](<https://whc.unesco.org/en/list/273/>) | Brief description |
| his_017 | Mongol Empire | [The Legacy of Genghis Khan](<https://www.metmuseum.org/exhibitions/listings/2002/genghis-khan>) | Exhibition overview |
| his_018 | printing press | [The Gutenberg Bible](<https://www.loc.gov/exhibits/bibles/the-gutenberg-bible.html>) | The Gutenberg Bible overview |
| his_019 | Italy | [Florence and Central Italy, 1400-1600 A.D.](<https://www.metmuseum.org/toah/ht/08/eustc>) | Overview |
| his_020 | Britain | [Early industry and Parliament](<https://www.parliament.uk/about/living-heritage/transformingsociety/tradeindustry/industrycommunity/overview/earlyindustry/>) | Early industry |
| his_021 | French | [The Oath (Napoleon's Coronation, 2 December 1804)](<https://www.napoleon.org/en/history-of-the-two-empires/paintings/the-oath-napoleons-coronation-2-december-1804>) | Painting description |
| his_022 | Geneva | [The Covenant of the League of Nations](<https://www.ungeneva.org/en/about/league-of-nations/covenant>) | Article 7 |
| his_023 | San Francisco | [Charter of the United Nations](<https://treaties.un.org/pages/ViewDetails.aspx?chapter=1&clang=_en&mtdsg_no=I-1&src=IND>) | Treaty heading |
| his_024 | 1989 | [Opening and fall of the Berlin Wall](<https://www.berlin.de/en/history/8482274-8619314-opening-and-fall-of-the-berlin-wall.en.html>) | Opening of the border |
| his_025 | Cuba | [Cuban Missile Crisis](<https://www.archives.gov/news/topics/cuban-missile-crisis>) | Overview |
| his_026 | Montgomery | [Rosa Parks](<https://www.nps.gov/people/rosa-parks.htm>) | Biographical opening paragraph |
| his_027 | 1994 | [Biography of Nelson Mandela](<https://www.nelsonmandela.org/biography>) | Presidency |
| his_028 | women's right to vote | [Women and the vote](<https://www.parliament.uk/about/living-heritage/transformingsociety/electionsvoting/womenvote/>) | Overview |
| his_029 | Abraham Lincoln | [Emancipation Proclamation (1863)](<https://www.archives.gov/milestone-documents/emancipation-proclamation>) | Document overview and transcript |
| his_030 | salt | [English Releases: Dandi March / Salt Satyagraha](<https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=48&relid=8343>) | Dandi March description |
| tech_011 | Not Found | [RFC 9110: HTTP Semantics](<https://www.rfc-editor.org/rfc/rfc9110.html>) | Sections 4.2.2 and 15.5.5 |
| tech_012 | 443 | [RFC 9110: HTTP Semantics](<https://www.rfc-editor.org/rfc/rfc9110.html>) | Sections 4.2.2 and 15.5.5 |
| tech_013 | connection-oriented | [RFC 9293: Transmission Control Protocol (TCP)](<https://www.rfc-editor.org/rfc/rfc9293.html>) | Section 2.2 |
| tech_014 | transfer email | [RFC 5321: Simple Mail Transfer Protocol](<https://www.rfc-editor.org/rfc/rfc5321.html>) | Section 1 |
| tech_015 | lossless | [Portable Network Graphics (PNG) Specification (Third Edition)](<https://www.w3.org/TR/png-3/>) | Abstract and scope |
| tech_016 | XML | [Scalable Vector Graphics (SVG) 2 - Introduction](<https://www.w3.org/TR/SVG2/intro.html>) | Section 1.1 |
| tech_017 | retrieve data | [PostgreSQL: Querying a Table](<https://www.postgresql.org/docs/current/tutorial-select.html>) | Section 2.5 |
| tech_018 | distinct primary-key values | [PostgreSQL: Constraints](<https://www.postgresql.org/docs/current/ddl-constraints.html>) | Section 5.5.4, Primary Keys |
| tech_019 | mutable | [An Informal Introduction to Python](<https://docs.python.org/3/tutorial/introduction.html>) | Sections 3.1.1 and 3.1.3 |
| tech_020 | // | [An Informal Introduction to Python](<https://docs.python.org/3/tutorial/introduction.html>) | Sections 3.1.1 and 3.1.3 |
| tech_021 | copy a repository | [git-clone Documentation](<https://git-scm.com/docs/git-clone>) | Description |
| tech_022 | TLS | [RFC 9110: HTTP Semantics](<https://www.rfc-editor.org/rfc/rfc9110.html>) | Sections 4.2.2 and 15.5.5 |
| tech_023 | volatile | [Memory Glossary](<https://www.kingston.com/en/memory/kingston-glossary>) | RAM |
| tech_024 | flash memory | [What is data storage?](<https://www.ibm.com/think/topics/data-storage>) | Solid-state drives |
| tech_025 | public and private keys | [What is asymmetric encryption?](<https://www.ibm.com/think/topics/asymmetric-encryption>) | Definition |
| tech_026 | 256 | [FIPS PUB 180-4: Secure Hash Standard](<https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf>) | Section 6.2, SHA-256 |
| tech_027 | eight | [RFC 791: Internet Protocol](<https://www.rfc-editor.org/rfc/rfc791.html>) | Glossary, Octet |
| tech_028 | 22 | [RFC 4253: The Secure Shell (SSH) Transport Layer Protocol](<https://www.rfc-editor.org/rfc/rfc4253.html>) | Section 4 |
| tech_029 | hyperlink | [HTML 4.01 Specification - Links](<https://www.w3.org/TR/html401/struct/links.html>) | Section 12.2, The A element |
| tech_030 | text-based | [RFC 8259: The JavaScript Object Notation (JSON) Data Interchange Format](<https://www.rfc-editor.org/rfc/rfc8259.html>) | Abstract |
| sci_021 | electromagnetic | [Anatomy of an Electromagnetic Wave](<https://science.nasa.gov/ems/02_anatomy/>) | Mechanical waves and Electromagnetic waves |
| sci_022 | require a material medium | [Anatomy of an Electromagnetic Wave](<https://science.nasa.gov/ems/02_anatomy/>) | Mechanical waves and Electromagnetic waves |
| sci_023 | carbon | [Carbon - Element information](<https://periodic-table.rsc.org/element/6/Carbon>) | Appearance and history |
| sci_024 | liquid | [Earth Facts](<https://science.nasa.gov/earth/facts/>) | Structure |
| sci_025 | igneous | [What are igneous rocks?](<https://www.usgs.gov/faqs/what-are-igneous-rocks>) | Opening definition |
| sci_026 | axial tilt | [What Causes the Seasons?](<https://spaceplace.nasa.gov/seasons/en/>) | The Short Answer and Earth's tilted axis |
| sci_027 | changing view of the Moon's sunlit half | [Moon Phases](<https://science.nasa.gov/moon/moon-phases/>) | Why Does the Moon Have Phases? |
| sci_028 | less | [Saturn Facts](<https://science.nasa.gov/saturn/facts/>) | Structure |
| sci_029 | nuclear fusion | [Sun Facts](<https://science.nasa.gov/sun/facts/>) | Structure |
| sci_030 | neutrons | [DOE Explains...Isotopes](<https://www.energy.gov/science/doe-explainsisotopes>) | Isotope definition |
