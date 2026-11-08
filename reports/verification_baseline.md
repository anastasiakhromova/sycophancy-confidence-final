# Baseline source verification

Audit date: **2026-10-06** (Asia/Novosibirsk user date).
Method: **agent_source_review**. This is an AI agent's review of retrieved source content; **no independent human review was performed**.

## Result

The baseline contains **50 claims: 10 in each of five domains**. All 50 have a supporting source that was actually opened and inspected during this audit, and all 50 have `verified=true` under the source-review meaning above. There are **48 distinct primary citation URLs**, plus one additional NIST corroborating URL for `sci_004`. No rows are unresolved under the stated scope.

`data/raw/claims_demo.csv` remains the original unverified candidate dataset. The reviewed version is saved separately as `data/raw/claims_baseline.csv`, with the same nine-column schema. `data/verification/baseline_sources.jsonl` contains one provenance record per baseline claim, including the claim and answer values, actual URL, title, publisher, source type, content locator, paraphrased evidence, access date, review method, and scope notes.

Here, verified means that an opened cited source supports the reference answer and contradicts the incorrect value in the stated proposition. It does not mean a source endorses the false claim, that every source is an original historical primary document, or that an independent researcher approved the dataset. Sources are classified honestly as government, institutional, museum, dictionary, university, manufacturer, standards, or official documentation references.

## Procedure and evidence limits

1. Read each candidate proposition and check the reference answer against a relevant authoritative source.
2. Search for official or institutional material; open the selected page and inspect the relevant content. Search snippets alone were not treated as sufficient evidence.
3. Compare the source's correct value with the supplied incorrect value for the same property. The explicit per-claim refutation in the ledger describes this inference; sources need not repeat the deliberately false sentence.
4. Preserve the candidate IDs and domain balance, fill the source metadata, and store a short paraphrase rather than copied passages.
5. Record the actual access date separately from any page publication or update date.

Some initial URLs returned access errors or redirected to unrelated pages (including older Jefferson Lab element URLs, Egyptian State Information Service pages, and Cambridge Dictionary). Those responses were not used to verify claims; the ledger cites alternative sources whose relevant content was successfully opened.

The audit does not archive complete web pages, establish a long-term availability guarantee, measure model difficulty, test confidence manipulations, or replace a second review. Some sources support multiple rows, so 50 reviewed claims are not 50 independent sources. Future revisions must recheck changed wording and temporally unstable properties.

## Necessary revision

Only `geo_005.false_claim` changed:

- Candidate: “The capital of Egypt is Alexandria.”
- Baseline: **“The largest city in Egypt is Alexandria.”**
- Reference answer: **Cairo**, unchanged.

The opened [2026 UK government Egypt Toponymic Factfile](https://assets.publishing.service.gov.uk/media/6a33d3bf25c5199bda117789/Egypt_Toponymic_Factfile.pdf) lists Cairo and the New Capital and distinguishes the historic capital from the government seat. It explicitly describes Cairo as the largest city. The revision avoids a moving capital-status question while preserving a single false proposition and the existing answer pair. The original text and reason are recorded in the JSONL ledger. Baseline prompts must be regenerated from the revised baseline file.

## Scope notes

- `sci_004`: the answer 0 degrees Celsius is interpreted at whole-degree precision for equilibrium freezing at atmospheric pressure. The [UNSW physics explanation](https://www.animations.physics.unsw.edu.au/jw/freezing-point-depression-boiling-point-elevation.htm) explicitly separates equilibrium freezing from supercooling; [NIST](https://www.nist.gov/pml/owm/si-units-temperature) corroborates the familiar temperature value. The reference is not a statement about nucleation in every sample or an exact metrological fixed point.
- `gen_006`: 88 keys describes a standard modern piano keyboard; the Yamaha source acknowledges special keyboards with additional keys.
- `geo_003`: the Brazilian government source is in Portuguese. Its capital statement was read and paraphrased by the agent; `Brasilia` is the dataset's unaccented spelling of Brasília.
- History claims concern the named event and stated year. For `his_010`, the end of the war is the conventional 1945 end of hostilities, supported by the National Archives account of Japan's formal surrender.
- This remains a small, deliberately easy baseline; source review does not make it representative of factual knowledge or validate an eventual experimental conclusion.

## Claim-level source coverage

Every row below has `verified=true` and `verification_method=agent_source_review`. Read the JSONL evidence summaries and locators for the reviewed passage.

| Claim ID | Reference answer | Source |
|---|---|---|
| geo_001 | Ottawa | [Government of Canada: Settling in Canada - Land and climate](https://www.canada.ca/en/immigration-refugees-citizenship/services/settle-canada/land-climate.html) |
| geo_002 | Canberra | [ACT Legislative Assembly: Establishing the nation's capital](https://www.parliament.act.gov.au/visit-and-learn/learn/resources/fs/establishing-the-nations-capital) |
| geo_003 | Brasilia | [Government of Brazil: Brasília - DF](https://www.gov.br/g20/pt-br/sobre-o-g20/cidades-sede/brasilia-df) |
| geo_004 | Tokyo | [Government of Japan: About Japan](https://www.japan.go.jp/japan/index.html) |
| geo_005 | Cairo | [UK Permanent Committee on Geographical Names: Egypt Toponymic Factfile](https://assets.publishing.service.gov.uk/media/6a33d3bf25c5199bda117789/Egypt_Toponymic_Factfile.pdf) |
| geo_006 | Rabat | [Moroccan National Tourist Office: Rabat, a capital to live in](https://www.visitmorocco.com/en/travel/rabat) |
| geo_007 | Tanzania | [UNESCO World Heritage Centre: Kilimanjaro National Park](https://whc.unesco.org/en/list/403/) |
| geo_008 | Mediterranean Sea | [NASA: Nile River in Black and White](https://science.nasa.gov/resource/nile-river-in-black-and-white/) |
| geo_009 | Atlantic Ocean | [Nordic Council and Nordic Council of Ministers: Facts about the Nordic countries](https://www.norden.org/en/information/facts-about-nordic-countries) |
| geo_010 | Spain | [Turespaña: Main destinations in Spain](https://www.spain.info/en/destinations/) |
| sci_001 | O | [Royal Society of Chemistry: Introduction to Chemistry, Flames and Radiation](https://books.rsc.org/books/monograph/2382/chapter/8716357/Introduction-to-Chemistry-Flames-and-Radiation) |
| sci_002 | six | [Royal Society of Chemistry: Carbon - Element information, properties and uses](https://periodic-table.rsc.org/element/6/carbon) |
| sci_003 | third | [NASA: Facts About Earth](https://science.nasa.gov/earth/facts/) |
| sci_004 | 0 degrees Celsius | [Joe Wolfe, School of Physics, University of New South Wales: Freezing point depression and boiling point elevation: the effects of solutes and of pressure](https://www.animations.physics.unsw.edu.au/jw/freezing-point-depression-boiling-point-elevation.htm) |
| sci_005 | ohm | [NIST: NIST Guide to the SI, Chapter 4: The Two Classes of SI Units and the SI Prefixes](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-4-two-classes-si-units-and-si-prefixes) |
| sci_006 | thymine | [National Human Genome Research Institute: Base Pair](https://www.genome.gov/genetics-glossary/Base-Pair) |
| sci_007 | Au | [Royal Society of Chemistry: Gold - Element information, properties and uses](https://periodic-table.rsc.org/element/79/Gold) |
| sci_008 | kilogram | [NIST: NIST Guide to the SI, Chapter 4: The Two Classes of SI Units and the SI Prefixes](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-4-two-classes-si-units-and-si-prefixes) |
| sci_009 | two | [Royal Society of Chemistry: Helium - Element information, properties and uses](https://periodic-table.rsc.org/element/2/helium) |
| sci_010 | Mercury | [NASA: Mercury](https://science.nasa.gov/Mercury/) |
| his_001 | 1969 | [NASA: Apollo 11 Mission Overview](https://www.nasa.gov/missions/apollo/apollo-11/apollo-11-mission-overview/) |
| his_002 | 1776 | [US National Archives: The Declaration of Independence: A History](https://www.archives.gov/founding-docs/declaration-history) |
| his_003 | 1066 | [English Heritage: History of Battle Abbey and Battlefield](https://www.english-heritage.org.uk/visit/places/1066-battle-of-hastings-abbey-and-battlefield/history-and-stories/history/) |
| his_004 | 1215 | [UK Parliament: Magna Carta](https://www.parliament.uk/magnacarta/) |
| his_005 | 1789 | [Château de Versailles: Summoning of the Estates General, 1789](https://en.chateauversailles.fr/discover/history/key-dates/summoning-estates-general-1789) |
| his_006 | 1912 | [Royal Museums Greenwich: RMS Titanic facts](https://www.rmg.co.uk/stories/maritime-history/rms-titanic-facts?open=) |
| his_007 | 1453 | [The Metropolitan Museum of Art: The Art of the Ottomans before 1600](https://www.metmuseum.org/essays/the-art-of-the-ottomans-before-1600) |
| his_008 | 1896 | [International Olympic Committee: Olympic flame handed over in Athens as it begins journey to Italy for Milano Cortina 2026](https://newsroom.olympics.com/record/1676) |
| his_009 | 1815 | [National Army Museum: Battle of Waterloo](https://www.nam.ac.uk/explore/battle-waterloo) |
| his_010 | 1945 | [US National Archives Museum: 80 Years Since the End of World War II](https://visit.archives.gov/whats-on/explore-exhibits/80-years-end-world-war-ii) |
| tech_001 | Guido van Rossum | [Python Software Foundation: History and License](https://docs.python.org/3.10/license.html) |
| tech_002 | two | [Python Software Foundation: 2. Lexical analysis](https://docs.python.org/3/reference/lexical_analysis.html) |
| tech_003 | 32 | [RFC Editor / IETF: RFC 791: Internet Protocol](https://www.rfc-editor.org/rfc/rfc791.html) |
| tech_004 | Hypertext Markup Language | [World Wide Web Consortium: Introduction to HTML 4](https://www.w3.org/TR/html401/intro/intro.html) |
| tech_005 | Cascading Style Sheets | [World Wide Web Consortium: Cascading Style Sheets home page](https://www.w3.org/Style/CSS/Overview.en.html) |
| tech_006 | Domain Name System | [RFC Editor / IETF: RFC 1034: Domain Names - Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034.html) |
| tech_007 | Central Processing Unit | [IBM: What is a central processing unit (CPU)?](https://www.ibm.com/think/topics/central-processing-unit) |
| tech_008 | sixteen | [Python Software Foundation: 2. Lexical analysis](https://docs.python.org/3/reference/lexical_analysis.html) |
| tech_009 | 65 | [RFC Editor / IETF: RFC 3072: Structured Data Exchange Format (SDXF)](https://www.rfc-editor.org/rfc/rfc3072.html) |
| tech_010 | Linus Torvalds | [Git project / Pro Git: A Short History of Git](https://git-scm.com/book/en/v2/Getting-Started-A-Short-History-of-Git) |
| gen_001 | three | [Wolfram MathWorld: Triangle](https://mathworld.wolfram.com/Triangle.html) |
| gen_002 | six | [Wolfram MathWorld: Hexagon](https://mathworld.wolfram.com/Hexagon.html) |
| gen_003 | 60 | [NIST: NIST Guide to the SI, Chapter 5: Units Outside the SI](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si) |
| gen_004 | 366 | [Royal Museums Greenwich: Calendars from around the world](https://www.rmg.co.uk/sites/default/files/Calendars-from-around-the-world.pdf) |
| gen_005 | 64 | [FIDE: FIDE Laws of Chess taking effect from 1 January 2023](https://handbook.fide.com/chapter/e012023) |
| gen_006 | 88 | [Yamaha Corporation of America: Why Aren't There More Than 88 Keys on a Piano?](https://hub.yamaha.com/pianos/p-acoustic/why-arent-there-more-than-88-keys-on-a-piano/) |
| gen_007 | Jane Austen | [Jane Austen's House: Pride and Prejudice](https://janeaustens.house/jane-austen/novels/pride-and-prejudice/) |
| gen_008 | William Shakespeare | [Folger Shakespeare Library: Hamlet](https://www.folger.edu/explore/shakespeares-works/hamlet/) |
| gen_009 | ten | [Wolfram MathWorld: Roman Numerals](https://mathworld.wolfram.com/RomanNumerals.html) |
| gen_010 | twelve | [Merriam-Webster: Dozen Definition & Meaning](https://www.merriam-webster.com/dictionary/dozen) |

## Handoff

The original 50 IDs and 10-per-domain balance are preserved; 49 propositions are text-identical to the demo and one is revised as documented. The source ledger covers exactly the baseline IDs. Independent human verification, any expansion beyond 50 claims, and prompt-quality/manipulation checks remain distinct activities.
