# Demo data

Two demo courses. The syllabus and the question paper are provided as files so
that the PDF and DOCX upload can be shown during the review. The Course Outcomes
have to be typed into the CO table in the app, so they are written out below for
copying.

Each course is given in a different file format, so both readers get exercised:

| Course | Syllabus file | Question paper file |
|---|---|---|
| ID2103 | `ID2103_syllabus.pdf` (PDF) | `ID2103_question_paper.docx` (DOCX) |
| CS2201 | `CS2201_syllabus.docx` (DOCX) | `CS2201_question_paper.pdf` (PDF) |

---

## Course 1 - ID2103

This is the same course as the **Load sample course data** button in the sidebar,
so you can either press the button or upload the files.

```
Course Code:  ID2103
Course Name:  Art & Aesthetics in Design
```

### Course Outcomes

| CO ID | CO Statement |
|---|---|
| CO1 | Explain fundamental concepts and principles related to art, aesthetics and design quality. |
| CO2 | Interpret and evaluate art in relation to identity, emotion and individual human experience. |
| CO3 | Analyze the relationship between art, design, society and everyday life. |

### Questions

| Q.No | Question | Marks |
|---|---|---|
| 1(a) | List the elements and principles of design. | 2 |
| 1(b) | Explain the three primary components of the Design Quality Triangle. | 3 |
| 1(c) | Discuss how they interact with each other in the context of product design with reference to a smart television. | 5 |
| 2(a) | Explore how personal identity, emotions, and individual experiences are communicated through different forms of art. | 4 |
| 2(b) | Why are some artworks revered across generations regardless of changing artistic trends? | 4 |
| 3(a) | Critically analyze how art acts as a transformative force in society by challenging norms and promoting social awareness. | 4 |
| 3(b) | Propose a public art installation for your campus that addresses a social issue, and justify your design choices. | 6 |

### Reference labels

Keep these on paper. Do not type them into the app - the whole point is that the
system works them out on its own.

| Q.No | CO | Bloom | Why |
|---|---|---|---|
| 1(a) | CO1 | L1 | plain recall of a list |
| 1(b) | CO1 | L2 | explain a concept in your own words |
| 1(c) | CO1 | L3, L4 | apply the concept to a product, then analyse the interaction |
| 2(a) | CO2 | L3, L4 | apply and analyse across art forms |
| 2(b) | CO2 | L5 | a judgement, even though it starts with "Why" |
| 3(a) | CO3 | L3, L4 | analyse a mechanism in society |
| 3(b) | CO3 | L6 | design something new and defend it |

These seven questions cover all six Bloom levels, L1 to L6.

---

## Course 2 - CS2201

A second, unrelated course. Useful in the review to show that the system is not
tuned to one subject.

```
Course Code:  CS2201
Course Name:  Data Structures and Algorithms
```

### Course Outcomes

| CO ID | CO Statement |
|---|---|
| CO1 | Explain the fundamental linear data structures such as arrays, stacks, queues and linked lists along with their basic operations. |
| CO2 | Apply appropriate searching, sorting and hashing techniques to solve computational problems. |
| CO3 | Analyze the time and space complexity of algorithms and compare alternative solutions. |
| CO4 | Design efficient solutions using trees and graphs for real world problems. |

### Questions

| Q.No | Question | Marks |
|---|---|---|
| 1(a) | Define a stack and list its basic operations. | 2 |
| 1(b) | Explain how a stack is used to evaluate a postfix expression. | 4 |
| 2(a) | Apply the quick sort algorithm to the list 42, 17, 93, 8, 56, 31 and show each partitioning step. | 5 |
| 2(b) | Compare the worst case time complexity of quick sort and merge sort, and justify which one you would choose for sorting a nearly sorted array. | 6 |
| 3(a) | Why is a hash table using separate chaining preferred over linear probing when the load factor is high? | 4 |
| 3(b) | Design a graph based solution to find the shortest delivery route for a courier service across a city, and analyze the time complexity of your solution. | 8 |
| 4(a) | Explain the rotations performed in an AVL tree when it becomes unbalanced after an insertion. | 5 |

### Reference labels

| Q.No | CO | Bloom |
|---|---|---|
| 1(a) | CO1 | L1 |
| 1(b) | CO1 | L2 |
| 2(a) | CO2 | L3 |
| 2(b) | CO3 | L4, L5 |
| 3(a) | CO2 | L5 |
| 3(b) | CO4 | L4, L6 |
| 4(a) | CO1 or CO4 | L2 |

`4(a)` is genuinely debatable between CO1 and CO4, which is a fair thing to admit
during the review rather than hide.

---

## Two things worth pointing out during the review

**Cosine similarity alone is not enough.** On the CS2201 paper, plain similarity
ranks `2(a)` and `4(a)` under **CO1**, because the wording mentions a *list* and
uses the verb *Explain*. The syllabus chunks that get retrieved for those two
questions are Unit 2 (sorting) and Unit 4 (AVL trees), which is the evidence the
LLM needs to correct the CO. That is the gap the project is about.

**The verb is not the level.** `2(b)` in ID2103 and `3(a)` in CS2201 both begin
with "Why", and both are Evaluate (L5), not Understand (L2). The prompt tells the
model to judge the whole cognitive task rather than the opening verb.
