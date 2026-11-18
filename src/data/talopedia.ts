// Talopedia articles for cities that have one. Keys are matched case- and
// diacritic-insensitively against city names, so "Chukyo" would find "Chūkyō".
//
// The article's address is not stored: it is the city's name without its
// diacritics, in lower case, words joined by hyphens, under TALOPEDIA
// (talopediaUrl). That is how the Talopedia names every article, so a city is
// added here by its name alone.
//
// `about` is the opening paragraph of the article, pasted by hand as plain
// text. It is escaped before display, so apostrophes and & are safe as-is.
//
// These pointed at the Google Docs the articles used to live in until 17 Nov
// 2026. Four cities had a doc and have no article on the site yet (Chūkyō,
// Mizuhara, Naginomiya, Takarazuka): they come back here when theirs is written.

export const TALOPEDIA = 'https://auroruse.github.io/the-talopedia/'

export interface TalopediaEntry {
  about: string
}

// A name as the Talopedia writes it into an address or a file name
export function talopediaSlug(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export function talopediaUrl(name: string): string {
  return TALOPEDIA + talopediaSlug(name) + '/'
}

export const talopedia: Record<string, TalopediaEntry> = {
  'Auritania City': {
    about: `Auritania City (Ciudad de Auritania, see-oo-DAHD deh ow-ree-TAH-nee-ah) is the capital and most populous city of Auritania, as well as the most populous city in Elysia. It is located in the Valley of Anahuac within the Anahuacan Plateau. The city has 16 boroughs or distritos, which are in turn divided into over 6,400 neighborhoods (colonias and barrios).`,
  },
  Axiom: {
    about: `Axiom, previously called Metro Regima, is the most populous city in Elysia. It is located at the northern end of Cygnus Bay on Regima Harbor. The city comprises 6 boroughs, each coextensive with its respective counties. It is the demographic and geographic center of the Northeast Megalopolis, and the Axiom Metropolitan area, the largest metropolitan area in Elysia by both population and urban area. Despite the Gestaltist reforms of the Unity State, Axiom continues to be a global centre of commerce, culture, technology, entertainment and media, scientific output, the arts, and fashion.`,
  },
  Eretz: {
    about: `Eretz is the capital and largest city of the Order of Shivon. It houses the Great Temple, a structure dating back thousands of years to the era of the First Hasmenionian Empire. According to Hasmonean tradition, this is the site where God instructed Zechariah to establish the Temple.`,
  },
  Nexus: {
    about: `Nexus is the capital city of the Elysian State of Unity. Located at the end of the Aquila Valley and along the Patawomeck river, Nexus stands as the Unity State's 4th-largest city in terms of population and GDP, with an urban population of 3,52 million as of 1935 and a GDP PPP of $414.95 billion, standing as an important hub of commerce and travel for the Elysian Eastern seaboard. It acts as the southern demographic and geographic center of the Northeast Megalopolis.`,
  },
  Pietari: {
    about: `Pietari is the capital and most populous city of the United Socialist States of Karjania. It is located on the shore of the Laatokka and Inkeri Lakes in northern Evria, where it's one of the region's largest cities. Its population exceeds 5 million, it's also the economic and cultural center of Karjania. Pietari doesn't belong to any subdivisions, its main administrative body is the Pietari City Council. Pietari has 5 football stadiums, a university, the largest square in Karjania and is the location where the Karjanian Communist Congress is held. It's also one of the historical centres of the traditional Routanmaa region, the most populated region in Karjania.`,
  },
  Shinkeisei: {
    about: `Shinkeisei is the capital of Nichirin and the second-most populous city in the world, with over 36 million residents across 94 wards. Situated at the head of Senpan Bay where the Sanzu, Kasuhara, and Hinode rivers converge, it serves as the seat of the Miyamoto Shogunate and headquarters of the Shogunate Navy. With a GDP exceeding $2.5 trillion, Shinkeisei is the world's largest metropolitan economy and home to 17 of Nichirin's 20 largest zaibatsu. Landmarks include the Palace of the Solar Halo, the Sōtenroku shrine district at the foot of Mount Sōten, and Zenbonsakura Station, the continent's most advanced railway terminal.`,
  },
}
