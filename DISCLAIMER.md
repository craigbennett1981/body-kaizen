# Disclaimer

Body Kaizen is provided **as is, without warranty of any kind** (see [LICENSE](LICENSE)). By using it you accept the
following.

**You are responsible for your own use of it.** You choose what to track, which services and AI assistant to
connect, where your data is stored and who can see it, and what you do with what the dashboard shows you. Those
decisions, and their consequences for your health, your accounts and your data, are yours alone. The authors and
contributors are not responsible for them.

**The AI assistant is a separate service.** Body Kaizen contains no AI. The assistant you connect is what reads
your messages and photos, identifies foods, estimates portions, adds new foods and their macros, writes coach
comments, and gives you feedback and advice. Body Kaizen then adds up whatever the assistant wrote and draws it.
So the accuracy of the food breakdowns, estimates and advice depends on that assistant. It is provided by its own
company under that company's terms, and Body Kaizen's authors and contributors are not responsible for anything
it says or does. AI assistants make mistakes, sometimes confidently: check what yours logs, and treat its advice
as a suggestion, not a verdict.

**Health.** Nothing Body Kaizen shows is medical advice. Scores, targets, readiness, "next move" lines and
suggestions, including anything an AI assistant tells you while logging, are rules of thumb that can be wrong.
Glucose, blood pressure and lab values are shown for interest, never for diagnosis or treatment decisions. Talk to a
doctor before changing your diet, training, medication or supplements, and about any reading that worries you.

**Thresholds.** The bands and cut-offs the dashboard judges you against (listed on its "How your numbers are judged" page and in
[docs/thresholds.md](docs/thresholds.md)) are taken from published guidelines where one exists and are otherwise
judgement calls. We make a best effort to get them right and to say where each one comes from, but guidelines
change and we can get them wrong. If you spot a problem, please
[raise a GitHub issue](https://github.com/craigbennett1981/body-kaizen/issues).

**Integrations.** The Garmin Connect and LibreLinkUp syncs use unofficial, community-maintained libraries. They are
not endorsed by, affiliated with, or supported by Garmin, Abbott, Hevy or any other company named here. Using them
may be against those services' terms of use and could, in principle, get your account rate-limited, locked or
suspended. They can stop working, or return wrong or incomplete data, without notice whenever those services
change. All trademarks belong to their owners.

These libraries (`garminconnect`, `pylibrelinkup` and their dependencies) are third-party software, written and
maintained by other people, and Body Kaizen's authors are not responsible for them. They handle your login details
and send them to those services. By connecting an integration you accept the terms of the service you connect to
and the licences of the software used to reach it, and you are responsible for checking that your use complies
with both.

**Security.** You are responsible for keeping your data and accounts secure:

- Body Kaizen sends nothing anywhere by itself. Your data goes only to the services you connect: your AI
  assistant, Garmin and Abbott when you sync, and any git host you push your data repository to. Each handles it
  under its own terms and privacy policy, which you agree to separately;
- the dashboard is built to run on your own computer and has **no login or access control**. Don't expose it to a
  network or the internet (it binds to `127.0.0.1` for this reason);
- login tokens and passwords for the integrations live on your computer (`~/.garminconnect`, your system
  keychain). Anyone with access to your user account can use them;
- an AI assistant you give access to your data folder can read, change and delete anything in it, and what you send
  it is handled under that provider's terms and retention policy;
- keep your data repository **private**; see [Keeping your data private in git](README.md#keeping-your-data-private-in-git).

**Loss of data.** Your data is only as safe as your backups. Syncs, imports, `compute.py`, an AI assistant or a bug
in Body Kaizen can overwrite, mis-file or delete entries, and the services you sync from can lose or change data
too. Keep your data folder in git, commit often, push it to a **private** remote or another backup, and check what
your assistant changes. The authors accept no liability for lost, corrupted, leaked or incorrect data, or for any
decisions made using it.
