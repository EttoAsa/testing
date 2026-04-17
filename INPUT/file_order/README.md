# File Orderings

Place JSON files here that define how files contained in the conversion source directory should be ordered.

### Considerations

#### Ensure files defined in the JSON exist in the source directory

Unlike when using the script's default file ordering, a file that is defined in a file ordering provided to the script that is not present in the conversion source directory will cause the script to fail. It is important to make sure that any files defined in a provided JSON are present.

#### Preceding numbers in top-level headings override the script ordering

In the top-level heading of each Markdown file, a leading number (for example, `# 4 Clause Heading) will override the file order defined in the script. It is important to ensure that:
1. No two Markdown source files use the same preceding number in their top-level heading. It is best to make sure the numbers correspond with the file's intended place in the overall hierarchy.
2. Numbering of non-standard clauses and annexes begins with **4**, because **1**, **2**, and **3** are reserved for the predefined clauses *Scope*, *References*, and *Definitions*.

### Example

The following example specifies the ordering of a few example files. An [empty template](../../templates/json/file_order.json) is provided for convenience.

``` json
{
  "clauses": [
    "clause-example1",
    "clause-example3",
    "clause-example2",
    "example4"
  ],
  "annexes": [
    "annex-example1",
    "annex-3",
    "example2"
  ]
}
```

This will ensure that the following file order is produced.

1. **Universal ETSI initial files**
    1. Intellectual Property Rights
    2. Foreword
    3. Modal verbs terminology
    4. Executive summary
    5. Introduction
2. **ETSI universal initial clauses**
    1. Scope
    2. References
    3. Definition of terms, symbols and abbreviations
3. **Clauses defined in the JSON**
    1. *clause-example1.md*
    2. *clause-example3.md*
    3. *clause-example2.md*
    4. *example4.md*
4. **Other clauses**[^1]
5. **Annexes defined in the JSON**
    1. *annex-example1.md*
    2. *annex-3.md*
    3. *example2.md*
6. **Other annexes**[^2]
7. **Universal ETSI final files**
    1. History

[^1]: If any other files exist in the conversion source directory whose filenames follow the format *clause-{text}.md*, they will be added alphabetically after the JSON-defined clauses.

[^2]: Similar to [^1], any files in the source directory that follow the format *annex-{text}.md* will be added alphabetically after the JSON-defined annexes.