EbookLib https://docs.sourcefabric.org/projects/ebooklib/en/latest/tutorial.html#introduction
epub-gen
BeautifulSoup



###DB:
Novel: - ID - Title - Author - Source_url - Synopsis - cover_path - Slug<Unique> - language

Chapter: ID - NovelID - Chapter_title - hash - last updated - Chapter_Order - content - htmlcontent

Tags: - ID - name<unique> - 

Tag_Link: - tag_id - Novel_id

--------------------------------------
###Processing the Epub
---
fetch epub from library

identify metadata equal to db

remember to download image and not refer to it using url

enter each valid metadata into db

-------------------------


###generate slug:

When your scraper grabs a novel, you can "slugify" the title using a simple bit of pseudocode:

Convert to lowercase.

Replace spaces with hyphens (-).

Strip out special characters (punctuation).

Append a random string or the source ID to the end to ensure it's truly unique (e.g., solo-leveling-8821).


###Creating Epub:

EPUB has some minimal metadata requirements that you need to fulfill. You need to define a unique identifier, the title of the book, and the language used. When it comes to the language code, the recommended best practice is to use a controlled vocabulary such as RFC 4646 - http://www.ietf.org/rfc/rfc4646.txt.

book.set_identifier("GB33BUKB20201555555555")
book.set_title("The Book of the Mysterious")
book.set_language("en")

book.add_author("John Smith")





