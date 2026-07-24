// Talopedia pages for cities that have one. Keys are matched case- and
// diacritic-insensitively against city names, so "Chukyo" finds "Chūkyō".
//
// `about` is the opening paragraph of the article's overview, pasted by hand.
// It is optional: an entry with only a `url` renders the link and no blurb.
// The text is escaped before display, so apostrophes and & are safe as-is.
//
// URLs are stored bare: no /u/0/ (routes visitors through whichever Google
// account they happen to have signed in first) and no ?ouid= (identifies the
// account that copied the link, and means nothing to anyone else).
// Every doc must be shared "Anyone with the link -> Viewer".

export interface TalopediaEntry {
  url: string
  about?: string
}

export const talopedia: Record<string, TalopediaEntry> = {
  Axiom: {
    url: 'https://docs.google.com/document/d/1p_AVNsWL0smEmQcNor8lbsRD_HRvfb0sXpj1epf3oPU/edit',
    about: `Axiom, previously called Metro Regima, is the most populous city in Elysia. It is located at the northern end of Cygnus Bay on Regima Harbor. The city comprises 6 boroughs, each coextensive with its respective counties. It is the demographic and geographic center of the Northeast Megalopolis, and the Axiom Metropolitan area, the largest metropolitan area in Elysia by both population and urban area. Despite the Gestaltist reforms of the Unity State, Axiom continues to be a global centre of commerce, culture, technology, entertainment and media, scientific output, the arts, and fashion.`,
  },
  Chukyo: {
    url: 'https://docs.google.com/document/d/1dWmylepjgRPsRUh1EzwyPVHm8-ND7UZmTxdtmRkfX5k/edit',
  },
  Mizuhara: {
    url: 'https://docs.google.com/document/d/18954-l9tH3rXZD2m5dzk9RM5nBrvsKSRCB2fr5YMB_A/edit',
  },
  Naginomiya: {
    url: 'https://docs.google.com/document/d/1-OGkHVbZ6hOARyd4c7Q1LuRxJT9KLKX4NsWfl9Bw85U/edit',
  },
  Pietari: {
    url: 'https://docs.google.com/document/d/18AwkLg4Fk67j4VRFQnVjYUFNoXEQdLjA0vYUnpPZn-c/edit',
    about: `Pietari is the capital and most populous city of the United Socialist States of Karjania. It is located on the shore of the Laatokka and Inkeri Lakes in northern Evria, where it's one of the region's largest cities. Its population exceeds 5 million, it's also the economic and cultural center of Karjania. Pietari doesn't belong to any subdivisions, its main administrative body is the Pietari City Council. Pietari has 5 football stadiums, a university, the largest square in Karjania and is the location where the Karjanian Communist Congress is held. It's also one of the historical centres of the traditional Routanmaa region, the most populated region in Karjania.`,
  },
  Shinkeisei: {
    url: 'https://docs.google.com/document/d/1t4Keh33LsXlkO_XV-ZZTi8puPdWctH1gO-PICYg6NqM/edit',
    about: `Shinkeisei is the capital of Nichirin. Located at the head of Senpan Bay, it is the second most populous city in the world, with an urban population of over 36 million in 1929. The city sits at the confluence of three major rivers (the Sanzu, Kasuhara, and Hinode), whose convergence creates a massive natural harbor that serves as both the headquarters of the Shogunate Navy and the second-largest commercial port in Nichirin after Takarazuka.`,
  },
  Takarazuka: {
    url: 'https://docs.google.com/document/d/1-bQViyEqRaqKBjwBc8T6AdZ92H-LJLIKmXlo2kOhwqQ/edit',
  },
}
