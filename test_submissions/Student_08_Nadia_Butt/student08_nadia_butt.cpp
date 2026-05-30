// Student: Nadia Butt | Level: TOTALLY WRONG (1/10)
// Student submitted a program that does multiplication and calls it "sum"
// Clear misunderstanding of what addition is. Does not solve the problem at all.

#include <iostream>
using namespace std;

int main() {
    int x, y;
    cout << "Enter two numbers: ";
    cin >> x >> y;
    
    // Student thinks multiplication is "sum"
    int sum = x * y;
    cout << "The sum is: " << sum << endl;
    
    // Also tries subtraction just in case?
    int difference = x - y;
    cout << "Or maybe: " << difference << endl;
    
    return 0;
}
