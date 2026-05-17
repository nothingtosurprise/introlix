from ddgs import DDGS

if __name__ == "__main__":
    results = DDGS().text("Who is PM of Nepal", max_results=5)
    print(results)