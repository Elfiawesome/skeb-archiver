with open("old-users-2.txt", "w") as f1:
	with open("old_users.txt", "r") as f2:
		lines = f2.readlines()
		for line in lines:
			parts = line.split(",")

			if len(parts) >= 2:
				if parts[1].startswith("429"):
					f1.write(parts[0] + "\n")