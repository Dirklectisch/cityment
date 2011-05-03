# Cityment #

Cityment is an experiment in data journalism. It analyses publications from a local dutch news channel (AT5) using sentiment analysis techniques resulting is either a positive or a negative score. The results are then grouped by city district.

Cityment can be seen in action at: http://www.cityment.nl

## Why? ##

The idea came about on local open data hack day called hackdeoverheid. We wanted create something off the beaten path, something different than a convenience application. So we set out to use natural language processing techniques to analyze a news feed and this is what we came up with. 

Originally the idea included combining the scores with other statistics. For example we wanted to see if a district that has high crime rates also has allot of crime reports in the press. We might still do that in the future but it is unfortunately not finished in the current version. Our vision for the product could be stated as: to gain insight in the subjectiveness of (local) journalism.

## How? ##

Cityment combines several programming languages and modules. It is a testament of how modern software architecture allows you to mesh up a broad range of languages. Here is an overview of some of it's components.

- Custom made crawler (Ruby)
- Rake DSL (Ruby)
- SentiWordNet lexical analysis (Python)
- Google Translate (HTTP API)
- CouchDB document storage (Erlang / JavaScript)
- Web standards front-end (HTML/CSS/JavaScript)
- Hosting on Heroku (Git powered backend)

These components are used to implemented the following functions.

1. Fetch all news items from the AT5 HTTP API
2. Convert news items to JSON
3. Insert news items into CouchDB
4. Translate items into english
5. Determine sentiment score
6. Group items by district (using javascript map/reduce function)
7. Display overview and items in browser

## Credits ##

Cityment is a project by Robert Massa (@Grepsy) & Dirk Geurs (@Dirklectisch). Special thanks go out to Marc Roos and Guido Veuger at AT5 for quickly responding to some critical bug reports.
