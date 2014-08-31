---
layout: post
title:  "What is MesaDB?"
date:   2014-08-23 23:23:36
categories: intro
---

Google's Mesa is a highly scalable analytic data warehousing system that stores critical measurement data related to Google’s Internet advertising business. Mesa is designed to satisfy a complex and challenging set of user and systems require- ments, including near real-time data ingestion and querya- bility, as well as high availability, reliability, fault tolerance, and scalability for large data and query volumes. Specifi- cally, Mesa handles petabytes of data, processes millions of row updates per second, and serves billions of queries that fetch trillions of rows per day. Mesa is geo-replicated across multiple datacenters and provides consistent and repeatable query answers at low latency, even when an entire datacen- ter fails.

MesaDB is our open source project, is inspired by Mesa. We are planning to build a simple, mesa-like database.

MesaDB will refer Google Mesa, C-Store by Michael Stonebraker, Vertica of HP, Monet, ect..., we will build a simple, strong, oriented-distributed, high-performance next generation database engine.

You can visit [Mesa.pdf](http://mesadb.com/upload/Mesa.pdf).

[jekyll-gh]: https://github.com/jekyll/jekyll
[jekyll]:    http://jekyllrb.com
