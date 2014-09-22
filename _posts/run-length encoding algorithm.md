# Runlength Encoding


##  介绍


**Edit by** <theseusyang@gmail.com>

游程編碼（RLE，run-length encoding），又称行程長度編碼或變動長度編碼法，是一種與資料性質無關的无损数据压缩技术。

變動長度編碼法為一種「使用固定長度的碼來取代連續重複出現的原始資料」的壓縮技術。


Runlength encoding replaces a value that is repeated consecutively with a token that consists of the value and a count of the number of consecutive occurrences (the length of the run). A separate dictionary of unique values is created for each block of column values on disk. (An Amazon Redshift disk block occupies 1 MB.) This encoding is best suited to a table in which data values are often repeated consecutively, for example, when the table is sorted by those values.

For example, if a column in a large dimension table has a predictably small domain, such as a COLOR column with fewer than 10 possible values, these values are likely to fall in long sequences throughout the table, even if the data is not sorted.

We do not recommend applying runlength encoding on any column that is designated as a sort key. Range-restricted scans perform better when blocks contain similar numbers of rows. If sort key columns are compressed much more highly than other columns in the same query, range-restricted scans might perform poorly.

The following table uses the COLOR column example to show how the runlength encoding works:


<table cellspacing="0" border="0"><colgroup><col class="col1"><col class="col2"><col class="col3"><col class="col4"></colgroup><thead><tr><th>Original data value </th><th>Original size (bytes) </th><th>Compressed value (token) </th><th>Compressed size (bytes) </th></tr></thead><tbody><tr><td>Blue </td><td>4 </td><td rowspan="2">{2,Blue} </td><td>5 </td></tr><tr><td>Blue </td><td>4 </td><td>0 </td></tr><tr><td>Green </td><td>5 </td><td rowspan="3">{3,Green} </td><td>6 </td></tr><tr><td>Green </td><td>5 </td><td>0 </td></tr><tr><td>Green </td><td>5 </td><td>0 </td></tr><tr><td>Blue </td><td>4 </td><td>{1,Blue} </td><td>5 </td></tr><tr><td>Yellow </td><td>6 </td><td rowspan="4">{4,Yellow} </td><td>7 </td></tr><tr><td>Yellow </td><td>6 </td><td>0 </td></tr><tr><td>Yellow </td><td>6 </td><td>0 </td></tr><tr><td>Yellow </td><td>6 </td><td>0 </td></tr><tr><td>Totals </td><td>51 </td><td> </td><td>23 </td></tr></tbody></table>