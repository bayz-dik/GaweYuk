import argparse
from onejob.service import OneJobService

service = OneJobService.demo()

def cmd_jobs(_):
    for item in service.list_jobs():
        src = ', '.join(s['name'] for s in item['sources'])
        print(f"{item['decision']:<6} {item['match_score']:>3}% match | {item['trust_score']:>3}% trust | {item['title']} — {item['company']} [{src}] | {item['id']}")

def cmd_job(args):
    item = service.get_job(args.id)
    for key, value in item.items():
        print(f'{key}: {value}')

def cmd_answer(args):
    result = service.suggest_answer(args.job, args.question)
    print(result)

def main():
    parser = argparse.ArgumentParser(prog='onejob')
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser('jobs'); p.set_defaults(func=cmd_jobs)
    p = sub.add_parser('job'); p.add_argument('id'); p.set_defaults(func=cmd_job)
    p = sub.add_parser('answer'); p.add_argument('--job', required=True); p.add_argument('--question', required=True); p.set_defaults(func=cmd_answer)
    args = parser.parse_args(); args.func(args)

if __name__ == '__main__':
    main()
