# Founder use cases

This starter is useful when a small team has documentation but repeatedly
answers the same customer questions.

| Use case | Example | What the starter contributes | What still needs a person |
| --- | --- | --- | --- |
| SaaS support drafting | “How do I invite my teammate?” | Finds the relevant guide and drafts a response with a quotation and revision. | Check correctness and send the response. |
| Customer onboarding | “Where do I export my data?” | Retrieves product instructions without making the customer search several documents. | Handle permissions and account-specific problems. |
| Developer-product documentation | “How should my integration handle HTTP 429?” | Combines exact terminology with semantic retrieval. | Validate code and deployment-specific advice. |
| Documentation gap discovery | “Do you offer phone support?” when no policy exists | Stores an insufficient-evidence question for review. Negative feedback enters the same queue. | Decide the policy and update the documentation. |
| Internal product enablement | New staff learning product behavior | Provides inspectable sources for draft explanations. | Review answers and maintain approved documentation. |

## Demo walkthrough

With the sample corpus ingested and the server running:

1. Expand a document on **FAQ** and search “export attachments”. This reads
   the stored corpus without generating an answer.
2. Check **Draft an answer with local AI** and ask “How do I invite a teammate?”
3. Read the draft, quotation, filename, revision and source lines together.
4. Ask “Do you offer phone support?” and inspect **Review queue**.
5. Select **Needs improvement** on an unhelpful draft and confirm the queue entry.
6. Open **Settings** to check the database and inspect the actual stored passage
   count and configured model names.

Generated text varies by model and hardware. Compare the actual answer to the
source; the demo does not pre-record a model answer or substitute synthetic
success for a failed request.

## First customer pilot

Choose one SaaS product with a small documentation set and a founder willing
to review answers. Collect 20–30 representative support questions, including
questions the documentation cannot answer. Have the founder score usefulness,
correctness, source relevance, and appropriate abstention.

Measure setup completion, time to first useful answer, use with the founder's
own documentation, and whether they return within seven days. Do not promise
a ticket-deflection percentage before observing actual usage.

An operator-assisted support tool is a suitable first pilot. Autonomous refunds,
account changes, legal/medical guidance, or a publicly exposed customer chatbot
are outside this starter's implemented scope.
